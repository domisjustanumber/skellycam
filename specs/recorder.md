# Phase 5 step 5a specification: the new video recorder

Status: proposed by an agent on 2026-11-19
([ADR-Q03C](../decisions/entries/Q03C-phase-5-step-5a-recorder-spec-and-test-list.md)). The user
reviews and accepts this spec and its test list before any code [R12]. The decisions R1 to R12 of the
user are accepted ([ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)). Section 18
gives each one in full.

## 0. How to read this spec

Marks:

- **[Rn]**: decision n of the user, 2026-11-19 (section 18,
  [ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)).
- **[SFF-n]**: requirement n of the skellyfileformat specification, draft v2, `spec/SPEC.md` of the
  repository `../skellyfileformat`, branch `main`, commit
  `d67679ada704caf55c64c2e279081d317205f354`. **[SFT-n]**: test n of `spec/conformance.md` of the
  same commit. A skellyfileformat entry is cited as "skellyfileformat ADR-XXXX".
- **[P-n]**: proposed change n to skellyfileformat (section 13). The recorder follows it. The user
  decides it [R6].
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md)
  ([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)).
- **[cap x.y]**, **[Dn]**, **[Un]**: section x.y, decision Dn and answer Un of
  [`windows-capture.md`](windows-capture.md)
  ([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md),
  [ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md),
  [ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)).
- **[P §n]**: section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`. **[M file]**: measured; the file
  holds the result. Each research file is on branch `dom/research` at commit fc95be447 of this
  repository. `RU/` is short for `research/skellycam_recording/recording_upgrade/`. The study of
  that folder is closed. Its evidence stays [R7].
- **[NV]**: not verified. Nobody measured it, or the evidence does not cover it.
- **[agent n]**: an agent filled a gap that the decisions, the format and the plan do not fix.
  Section 16, item n, lists each one. Section 17 holds the questions for the user.

This spec uses British spelling. Code names come from branch `dom/recorder` at commit fd64a8e5a
(the same tree as `dom/native-jpeg` at that commit). The spec cites files, not line numbers.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Step 5a replaces the old recorder (decoded image in, H.264 MP4 out) with a writer of the
skellyfileformat take folder [R1]. Each camera gets one MKV file with the camera JPEG bytes
unchanged and one CSV timing sidecar. The take gets a manifest and a capture info JSON [SFF-716].
The files survive a hard stop of a camera process. Thus the three interim rules U4, U5 and U12 of
phase 3 go [R1].

### 1.2 Scope

| Step | Delivers |
|---|---|
| 5a (this spec) | The video writer, the timing CSV, the manifest, the capture info as far as 5a can fill it, and the end of a take [R1]. A self-contained module with its own tests, fed by synthetic JPEG frames, in the worktree of branch `dom/recorder` [R10]. The measurements of R11. After step 3a of phase 3 is joined, one connection commit joins the module to the shared loop (section 10) [R10]. |
| 5d (later) | Camera identity from the operating system: `camera_key` from the identity string of SFF-752, the label of SFF-720 and the full capture info (`device`, `user_name`, all controls of SFF-802, `exposure_step`) [R1, R8]. |
| 5b (later) | Audio in Opus in fragmented MP4 with its timing CSV, and the timestamp fit of each sidecar (the fit lines of SFF-775) [R1]. |
| 5c (later) | Repair of a take after a crash (SFF-793 to SFF-798) [R1]. Step 5a holds only the small part that it needs: it finishes the files of one camera with missing rows and the closing lines (7.4) [R4]. |

### 1.3 Non-goals

- Audio. Step 5a writes no audio file. The WAV goes [R5]. Opus comes in 5b [R1]. Question Q1 asks
  what a record start with a microphone does between 5a and 5b.
- The fit lines. A finished sidecar of 5a has no `# fit` line (6.4) [R1].
- The repair of a crashed take, and the question of SFF-793 at start-up (5c) [R1].
- Camera identity from the operating system (5d) [R1, R8].
- The canvas player (phase 6). The app cannot show new takes until then [R9].
- The reader of the new format, the "upgrade recording" converter and the playback of new takes
  (phase 6) [P §8].
- A change of the shared loop before step 3a is joined [R10].
- The removal of the lockstep gate (phase 8) [P §8].
- H.264 capture [SFF-734].

### 1.4 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| The format: one MKV with `V_MJPEG` per camera, one CSV per camera with a CRC and a flush per row, the manifest, the capture info, the folder layout | skellyfileformat SPEC draft v2; earlier decisions of section 18 | Sections 6 and 7 cite each rule. |
| One writer thread per camera process; a bounded queue of about 3 s; a full queue slows capture and never drops a frame; a stall over the limit ends the take with an error; a write error finishes the sidecars and the manifest for the frames written | [P §6], section 18 | Section 5. |
| PyAV 19.0.2 for the MKV | [P §6], `pyproject.toml` (`av==19.0.2`) | Section 6.3. |
| What the writer receives per frame | [ring 5.1], [R10] | Section 4.1. |
| Recorder first, then the ring write | [ring 5.3] | Section 10. |
| Read old formats, never write them | section 18 | Section 8.3. |
| Opus in fragmented MP4 for audio | section 18 | Step 5b. |
| Camera states, dead camera, hang, gate | [cap 5.2, 6.6, 8] | Sections 7 and 10. |

R2 replaces the plan sentence "one camera fails mid-take: the whole take stops" [P §6]. R1 to R4
replace the interim rules U4, U5 and U12 [cap 5.5, 5.7, 6.6]. Section 14 lists the sentences of
`windows-capture.md` that change.

### 1.5 Terms

| Term | Meaning |
|---|---|
| take | The files of one recording [SFF-716]. In the code of today, a "recording". |
| take folder | `<recording_directory>/<recording_name>` of the start request. |
| `<rec>` | The recording name: `recording_name` of the start request [SFF-715]. |
| take level | The part of the module in the main process: folder, manifest, capture info, lock, the end of the take. |
| camera level | The part of the module in a camera process: queue, writer thread, MKV, CSV rows. |
| frame | One `RecorderFrame` (4.1). |
| damaged frame | A frame with a bit of the error mask 0x0F of [ring 4] in `flags` [R3]. |
| block | One `SimpleBlock` of an MKV, with one JPEG [SFF-733]. |
| row | One data row of a CSV [SFF-744]. Row k is multi-camera frame k [SFF-754]. |
| missing row | A row with the flag `missing` [P-1]: a row with no block. R2, R3 and R4 call it a "gap row". |
| frame count of the take | The number of rows of every CSV of the take at its end (7.6). |
| dead camera | A camera in the state `dead` of [cap 8.1], also after a hang [cap 6.6]. |
| stall limit | The longest time that `give` may wait for space in the queue (5.3). |

## 2. Done list

Step 5a is done when:

1. The tests of the kinds unit and process of section 12 pass on Windows, Linux and macOS (12.1).
2. The conformance subset of 12.3 gives only the expected results of that section.
3. The measurements of section 11 ran, and the user decided the queue size and the stall limit from
   the results [R11].
4. The user decided the proposals P-1 to P-6 of section 13 [R6]. The tests follow each decision.
5. After step 3a is joined: the connection commit of section 10 is in, the tests T-REC-38 to T-REC-45
   pass, and the edits of section 14 are made in `windows-capture.md` by an accepted entry.

## 3. Module layout

The module is new. It imports no code of the old recorder [agent 1]. It has two levels: the take
level in the main process and the camera level in each camera process [agent 2]:

| Path | Content |
|---|---|
| `skellycam/core/take_recorder/frame.py` | `RecorderFrame` (4.1). |
| `skellycam/core/take_recorder/take.py` | The take level: `start_take`, `Take`, `CameraTakeSpec`, `TakeSummary` (4.2). |
| `skellycam/core/take_recorder/camera_writer.py` | The camera level: `CameraTakeWriter`, `CameraTakeResult`, the queue and the writer thread (4.3, 5). |
| `skellycam/core/take_recorder/mkv.py` | The PyAV calls (6.3). |
| `skellycam/core/take_recorder/sidecar.py` | Header, row, footer and CRC of the CSV; the read of a CSV for the end of the take (6.4, 8.1). |
| `skellycam/core/take_recorder/completion.py` | The completion of the files of one camera (7.3, 7.4). |
| `skellycam/core/take_recorder/folder_files.py` | Manifest, capture info, the whole-file write and the lock (6.5 to 6.7). |
| `skellycam/core/take_recorder/stop_stats.py` | The fields of the stop response, from the CSVs (8.2). |
| `skellycam/tests/take_recorder/` | The tests of section 12, the synthetic JPEG source and the conformance adapter (12.3). |

Dependencies: only what `pyproject.toml` pins today: `av==19.0.2`, the standard library (`zlib`,
`threading`, `queue`, `json`, `hashlib`, `uuid`, `msvcrt` or `fcntl`), and `opencv-python` in the
tests only, to make synthetic JPEGs. No new package.

## 4. Public interface

### 4.1 `RecorderFrame` [R10]

The writer input is the list of R10, with the names of [ring 5.1]. It is a frozen dataclass with
slots:

| Field | Type | Use in 5a |
|---|---|---|
| `payload` | `bytes` | The JPEG of the camera, unchanged [SFF-734]. The object that the capture layer made. No copy (5.1). |
| `frame_number` | int | Not written. The camera writer checks that it increases. |
| `arrival_ns` | int | Absolute host-clock time. The CSV holds it minus the take start [SFF-755]. |
| `sample_ns` | int | Absolute host-clock time, or `NO_SAMPLE_NS` of the ring package. `NO_SAMPLE_NS` gives an empty field [SFF-755]. |
| `source_frame_number` | int | The CSV column `source_frame_number` [SFF-755], and the flags `gap` and `repeat` [SFF-756]. |
| `flags` | int | The ring flags of the capture check [ring 4, 5.2]. An error bit gives a missing row (7.2) [R3]. |
| `delivered_len` | int | Not written. The capture check already compared it [ring 5.2]. |
| `rotation_cw_deg` | int | Must equal the rotation of the take spec. Else `give` raises `ValueError` [agent 33]. |

### 4.2 Take level (main process)

```python
take = start_take(folder, rec, cameras, *, writer, clock=None, lock_timeout_s=10.0,
                  queue_seconds=3.0, stall_limit_s=10.0) -> Take
spec = take.camera_spec(camera_id) -> CameraTakeSpec
summary = take.finish(results, *, ended_by_error=None) -> TakeSummary
```

- `folder` is the take folder (a `pathlib.Path`). It must not exist, or it must be empty [SFF-719]
  [agent 16].
- `rec` is `<rec>`. `start_take` refuses a value that breaks SFF-715.
- `cameras` is a list of `TakeCamera`, in the order of `group_position` [agent 19]: `camera_id`,
  `nominal_rate` (`num`, `den`) [agent 20], `width` and `height` of the opened mode,
  `rotation_cw_deg`, the capture-info facts of 6.6, and `capture_format`.
- `writer` is the writer string, `skellycam <version>` [SFF-712].
- `clock` is a test seam: two callables for the host clock and UTC. The default is
  `time.perf_counter_ns` and `time.time_ns`.
- `start_take` creates the folder and the media folder. It reads the take start (6.4), writes the
  capture info JSON, then the manifest with `state` `recording`, both under the lock [SFF-724,
  SFF-801]. It returns after the two writes. A refusal raises `ValueError` before the first write.
  A lock timeout raises `TimeoutError` before the first write [agent 15].
- `camera_spec` gives the picklable `CameraTakeSpec` of one camera: the paths of its MKV and CSV,
  the header values of 6.4, the queue size, the stall limit and the rotation.
- `finish` takes one `CameraTakeResult` or `None` for each camera. `None` means that the camera
  process ended without a result (7.4). `finish` runs the end of the take (8.1) and returns a
  `TakeSummary`: the stop response fields of 8.2, the per-camera counts and the warnings.
  `ended_by_error` is `None` or the text of the error that ended the take (5.3, 5.4).

### 4.3 Camera level (camera process)

```python
writer = CameraTakeWriter.start(spec) -> CameraTakeWriter
writer.give(frame) -> None
result = writer.end() -> CameraTakeResult
```

- `start` opens the MKV and the CSV, writes the CSV header and the column line, and starts the
  writer thread. It returns before the first frame.
- `give` puts the frame in the queue. It returns at once when the queue has space. When the queue is
  full, `give` waits for space, at most the stall limit (5.2, 5.3) [agent 3]. It never drops a frame.
  After the stall limit, it raises `RecorderStalled`. After a write error of the writer thread, it
  raises `RecorderWriteError` at once (5.4).
- `end` puts the end marker in the queue, waits until the writer thread has written each queued
  frame, closes the MKV, writes the rows that wait (6.3), forces both files to disk, and closes them
  (5.6). It writes no footer: the take level writes each footer (8.1) [agent 11]. It returns a
  `CameraTakeResult`. `end` waits at most the stall limit for the writer thread. After that, it
  returns a result with `error="writer did not finish"`. The camera process then reports the result
  and ends with `os._exit`, as after a hang, because its writer thread can still write [R4]. The take
  level treats the camera as in 7.4.
- `CameraTakeResult` [agent 32]: `camera_id`, `rows` (rows written), `blocks`, `last_block_row` (the
  position of the last row with a block, or `None`), `queue_high_water` (frames),
  `give_wait_count`, `give_wait_ms_total`, `give_wait_ms_max`, `damaged_count` and `error` (`None` or
  a text).
- The writer is not reusable. A call of `give` before `start` or after `end`, or a second `end`,
  raises `RuntimeError`.

### 4.4 Threads

| Thread | Calls |
|---|---|
| Camera loop thread (camera process) | `start`, `give`, `end` |
| Writer thread (camera process) | The MKV mux, the row writes, the fsync (5.6). Nothing else. |
| Main process, the task of the camera group | `start_take`, `camera_spec`, `finish` |

The module does not depend on the gate, the ring or IPC. Tests call all three levels in one
process [R10].

## 5. Writer thread and queue

### 5.1 The queue

- One `queue.Queue` for each camera writer. Its size is ⌈`QUEUE_SECONDS` × `num` / `den`⌉ frames
  [agent 4]. `QUEUE_SECONDS` is 3.0, the starting value of R11 and of [P §6]. Example: 90 frames at
  30/1, 180 frames at 60/1.
- The queue holds the `RecorderFrame` objects. Each one holds the same `bytes` object that the
  capture layer made and that the ring writer copies into its slot. The recorder makes no copy
  [ring 5.7] [R10].
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
     `gap` [SFF-756]. These are the "gap rows" of [P §6].
- With the OpenCV source (pull, Linux and macOS until phase 7), the driver drops the frames and
  `source_frame_number` counts grabs [cap 4.2]. Thus the gap does not show in the flag. It shows only
  in `arrival_ns` (section 15.3).
- The camera writer counts each wait (`give_wait_count`, `give_wait_ms_total`, `give_wait_ms_max`)
  and the queue high-water. The camera process logs them at the end of the take. The camera status
  shows them (section 10) [P §6].

### 5.3 The stall limit

- The stall limit is the longest time that one `give` call waits [agent 3]. Its starting value is
  10 s [P §6, R11]. Section 11 measures it before the value is fixed [R11].
- After the limit, `give` raises `RecorderStalled`. The frame in hand is not written.
- "The take ends with an error" [P §6] means:
  1. The camera process reports `RecorderStalled` with its camera ID to the main process. Then it
     calls `end` (4.3). The writer thread can still be blocked on the disk. `end` waits at most the
     stall limit (4.3).
  2. The main process ends the take for every camera, as a stop request does [agent 24]. The other
     cameras record to the last frame of the take and end normally.
  3. `Take.finish` runs with `ended_by_error`. The manifest gets the warning `take_error` [P-4].
     Each camera gets missing rows to the frame count of the take (7.6).
  4. The app keeps running. A new take can start [P §6].

### 5.4 A write error

- An exception of the writer thread (for example `OSError` for a full disk) stops that writer
  thread. It records the error, closes what it can and ends. The next `give` raises
  `RecorderWriteError` at once [P §6].
- The camera process reports it. The main process ends the take for every camera, as in 5.3 items
  2 to 4 [P §6] [agent 24].
- The take level finishes the files of that camera for the frames written: the completion of 7.4.
  Then it writes the manifest with the warning `take_error` [P §6, P-4].
- When the take level cannot write either (the disk is full), the files stay unfinished and the
  manifest stays `recording`. Step 5c repairs such a take (section 9).

### 5.5 No thread spins

Each wait of the module blocks on a condition, a queue, a lock call or a process join, with a timeout
[ring 8.10]. The writer thread waits in `Queue.get()`. No loop polls without a block. The writer
thread is a non-daemon thread with the name `take-writer-<camera_id>`. The end marker in the queue is
`None` [agent 5].

### 5.6 What goes to disk and when

| Data | Write | Forced to disk |
|---|---|---|
| A block | One `mux` call with `flush_packets=1`. The muxer gives block k to the file when block k+1 comes, or at close [M `RU/results/write_throughput/FINDINGS.md` §2.3: 29 of 30 frames on disk with the writer open]. | With the CSV, once a second [SFF-788] |
| A row | One `write` call on an unbuffered file, with its LF [SFF-744] [agent 8]. Row k is written after block k is in the file (6.3) [agent 7]. | Once a second [SFF-788] |
| The fsync | `os.fsync` of the MKV descriptor, then of the CSV descriptor, on the writer thread, after a row write, when 1 s or more passed since the last fsync [agent 9]. Never on the camera loop thread. | — |
| The end of a camera | `end`: close the MKV, write the last rows, fsync both files, close them. | At `end` |
| Manifest, capture info | Whole-file write (6.7) [SFF-786]. | Each write |

The research measured a flush per row at +1.9 µs p50, and an fsync of two files every 30 frames
at p50 16.1 µs, p99 883 µs and a worst frame of 4.2 ms, for one writer on one NVMe drive
[M `RU/results/crash_resilience/FINDINGS.md` §2.11]. The cost for 16 writers is [NV]. Section 11
measures it [R11].

## 6. The files of a take in 5a

### 6.1 Folder layout and names

```
<take folder>/
  recording_manifest.json          6.5 [SFF-724]
  <rec>_info.json                  6.6 [SFF-801]
  .processing.lock                 6.7 [SFF-789]
  synchronized_videos/
    <rec>.<label>.mkv              6.3, one for each camera [SFF-732]
    <rec>.<label>.csv              6.4 [SFF-741]
```

- Each name is exact [SFF-716]. No other file and no other folder [SFF-719, SFF-722].
- Step 5a writes no audio file and no `<rec>.audio.csv`. `audio_count` is 0 and the manifest
  `audio` is null [SFF-749, SFF-723] [R5].
- `<rec>` is fixed at the start [SFF-715]. No program renames a file of the take [SFF-717].

### 6.2 Keys and labels before 5d [R8]

- Each camera's files are named from today's `camera_id` [R8]. Today `camera_id` is 4 hexadecimal
  characters [cap 7.2], and SFF-753 refuses a label that is not 6 to 8 of them. Thus [agent 10]:
  - `camera_key` = `camera_id` + the first 12 hexadecimal characters of the SHA-256 of the UTF-8
    bytes of `camera_id`. It has 16 lowercase hexadecimal characters [SFF-752 form].
  - `camera_label` = the first 6 characters of `camera_key` [SFF-720]. It starts with `camera_id`.
  - Two cameras of one take never have one `camera_id` [D13]. Thus their labels differ, and the
    7- and 8-character rule of SFF-720 never applies.
- The capture info marks the key as provisional with `key_origin` `"provisional"` [P-5] [R8].
- A reader finds the files through the manifest `cameras` items (`video`, `timing`), not by a
  guess of the name [R8, SFF-730].
- Step 5d changes the key to the identity string of SFF-752 and the label to SFF-720 [R8].

### 6.3 The camera file (MKV)

PyAV calls. This is the byte-exact recipe of the research
[M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1; `RU/results/EVIDENCE_INDEX.md` §2.1]:

```python
raw = open(mkv_path, "xb", buffering=0)                       # [agent 6]
container = av.open(raw, mode="w", format="matroska",
                    options={"flush_packets": "1"})
stream = container.add_mux_stream("mjpeg", rate=Fraction(num, den),
                                  width=width, height=height)
# for block b:
packet = av.Packet(frame.payload)
packet.stream = stream
packet.time_base = Fraction(1, 1000)
packet.pts = packet.dts = (2 * b * den * 1000 + num) // (2 * num)
container.mux(packet)
# at the end:
container.close()
raw.close()
```

- `add_mux_stream` with `av.Packet` and `mux`. Never `add_stream_from_template`: it lost frames in
  MP4 and MOV and gave `EINVAL` in AVI [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1]. Never
  `add_stream(codec)` with extradata [`RU/results/write_throughput/FINDINGS.md` §4 item 12]. Width
  and height are mandatory [M same JP file]. The evidence passes them by position; the keyword form
  above is [NV] until T-REC-34.
- `flush_packets=1` on the container [`RU/results/crash_resilience/FINDINGS.md` §4 item 2]. No
  empty packet after each frame: that trick loses no frame on a kill, but a killed file then seeks
  one frame late and a finished file does not seek to its last frame
  [M `RU/results/EVIDENCE_INDEX.md` §2.2; `RU/results/crash_resilience/FINDINGS.md` §2.2].
- A Python file object, not a path [agent 6]. Thus the writer owns the descriptor for `os.fsync`
  [SFF-788] and for `tell()`. PyAV has no flush call [M `RU/results/write_throughput/FINDINGS.md`
  §2.3], and the research found no way to fsync the MKV of a path-based writer
  [`RU/results/crash_resilience/FINDINGS.md` §4 item 10]. The kill behaviour of a file-object
  writer was not tested (same file, §2.11). T-REC-KILL tests it (section 11).
- One track, `V_MJPEG`, track number below 128 [SFF-732]. One block for each stored frame, a
  `SimpleBlock` with the keyframe flag; FFmpeg sets the flag for an intra-only stream
  [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1] [SFF-733]. No lacing [SFF-733].
- The JPEG bytes are the bytes of the camera [SFF-734, SFF-737]. Section 10 item 2 gives the
  hand-over that keeps them unchanged.
- No rotation element and no EXIF tag. The pixels are in sensor orientation [SFF-735].
- Time base 1/1000; TimestampScale 1,000,000 [SFF-736]. The container time of block b is
  ⌊(2 × b × `den` × 1000 + `num`) / (2 × `num`)⌋ ms, where b counts the blocks of the file from 0
  [P-2]. Thus a missing row leaves no hole in the container times. OpenCV and Blender count the
  frames of a file with index times exactly, also when frames drop
  [M `RU/results/blender_mkv/FINDINGS.md`; `RU/results/crash_resilience/gapfill/GF02_container_matrix.md`].
  Question Q2 asks the user to confirm this choice.
- `DefaultDuration` is ⌊10^9 × `den` / `num`⌋ ns [SFF-736]. T-REC-04 checks that PyAV writes it.
- `start_take` refuses a nominal rate above 1000 frames per second [SFF-736], and a `num` or `den`
  outside 1 to 2^20 [SFF-750]. It refuses a camera whose `capture_format` is H.264 [SFF-734].
- The track size is the width and height of the opened mode [agent 26].
- Live byte offsets [SFF-757] [agent 7]:
  1. The muxer gives block b to the file only when block b+1 comes, or at close (5.6).
  2. After the `mux` call of block b+1 returns, the end of the payload of block b is `raw.tell()`.
     Its `byte_offset` is that position minus the payload length. The writer then writes row b and
     each missing row after it that waits.
  3. For the last block, the writer notes `raw.tell()` before `container.close()`. After the close,
     it reads the bytes from that position for the payload length plus 64 bytes, finds the payload
     and checks that each byte is equal. Then it writes the last row.
  4. The method is [NV]: it assumes that a `mux` call writes nothing after the payload of the block
     that it gives to the file. T-REC-10 checks each offset, live and after close, on each OS. This
     is the desk test DT5 of SFF-757.
- After a process kill, each written row has a block on disk. The block of the last frame given to
  the muxer, and each frame in the queue, are lost [M `RU/results/EVIDENCE_INDEX.md` §2.2: MKV with
  `flush_packets` lost 1 frame per kill in 48 kills].

### 6.4 The timing sidecar (CSV)

The file is opened with `open(csv_path, "xb", buffering=0)` [agent 8]. Each write is one complete
line: header lines and the column line at `start`, one row for each frame, the footer lines at the
end of the take (8.1).

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
| `camera_key`, `camera_label` | 6.2 [R8]. |
| `nominal_rate` | `num/den` [SFF-750] [agent 20]. |
| `display_rotation` | `rotation_cw_deg` of the camera config [SFF-751]. |

Rows:

| Column | 5a value |
|---|---|
| `frame` | The position: 0 in the first row, +1 in each row [SFF-754]. |
| `source_frame_number` | `frame.source_frame_number`; empty in a missing row with no frame [P-1]. |
| `arrival_ns` | `frame.arrival_ns − take_start_host_ns` [SFF-755]; empty in a missing row with no frame [P-1]. |
| `sample_ns` | `frame.sample_ns − take_start_host_ns`, or empty for `NO_SAMPLE_NS` [SFF-755]. Thus the Media Foundation sample time of [D28] goes into the CSV. |
| `flags` | 7.1 and 7.2 [SFF-756, P-1]. |
| `byte_offset`, `byte_size` | The JPEG payload of the block [SFF-757]; empty in a missing row [P-1]. |
| `crc32` | The CRC-32 of the bytes of the row before the comma that comes before it, 8 lowercase hexadecimal characters [SFF-744, SFF-704]. |

- Integers in the form of SFF-701. No field is quoted, and no field holds a comma or a space
  [SFF-741]. UTF-8 with no byte order mark, LF line ends [SFF-700].
- Example rows: a normal row, a row after two replaced frames (`gap`), a damaged frame, a dead
  camera:

  ```
  0,1000,1203311,1180002,0,4127,61234,5b1e0c2a
  1,1003,1303311,1280002,1,65438,60911,0c41aa07
  2,1004,1336644,1313335,16,,,9e01b2c3
  300,,,,16,,,77a0f1d2
  ```

  The CRC values above are not real. T-REC-08 computes the real ones.

Footer lines, written by the take level at the end of the take (8.1) [SFF-745]:

```
# repair cut_bytes=<n> media_cut_bytes=<m> repair_writer=skellycam 2.0.0    (only after 7.4)
# end rows=<R> gaps=<G> filled=0 encode_skips=0 missing=<M>
```

- `rows`, `gaps`, `filled` and `encode_skips` follow SFF-758. `missing` is the number of rows with
  the flag `missing` [P-1] [R3].
- No `# fit` and no `# fit_segment` line in 5a [R1]. SFF-775 requires them at a normal end. Step 5b
  adds them. Until then, a reader gives the player time `arrival_ns` and the file warning
  `missing_fit` [SFF-781]. Section 15.4 lists this as a known gap of 5a.
- A sidecar without its `# end` line is unfinished [SFF-747]. A reader uses its complete rows
  [SFF-746].

### 6.5 The manifest

`recording_manifest.json` has the members of the table of section 5 of the format, in that order
[SFF-723]. The values in 5a:

| Member | 5a value |
|---|---|
| `skellyfileformat` | `"recording_manifest"` |
| `format_version`, `format_prerelease`, `writer` | As in 6.4 [SFF-707, SFF-712]. |
| `take_uuid`, `recording_name` | As in 6.4; `<rec>`. |
| `purpose` | `"motion_capture"` [agent 17]. |
| `state` | `"recording"` from `start_take`; `"finished"` from `finish` [SFF-724]. |
| `cameras` | One item for each camera, in order of `group_position`: `camera_key`, `camera_label`, `group_position`, `video`, `timing` (the two paths of 6.1), `calibration_camera` null [SFF-723]. |
| `audio` | null [R5]. |
| `calibration` | null. |
| `files` | One item: `{"path": "<rec>_info.json", "role": "capture_info", "owner": "skellycam", "sha256": <SHA-256 of the file>}` [SFF-723]. |
| `warnings` | `[]` at the start. At the end: `camera_gap` for each camera with `gaps` > 0 [SFF-727]; `camera_dead` for each dead camera [P-4] [R2, R4]; `take_error` when an error ended the take [P-4] [P §6]. `source` is `"skellycam"`. |
| `privacy` | `fields`: `/camera_configs/<key>/device/os_name` of the capture info when not null, `utc_offset_min` of each timing sidecar, `/recording_name` of the manifest; sorted [SFF-881, SFF-882]. `media_shows_people`: `true`. |
| `summary` | SFF-728. In the state `recording`: each `duration_s`, `stored_px`, `gaps` and `filled` is null. At the end: computed from the CSVs; `stored_px` is the size of the first stored JPEG, from its SOF segment; `user_name` and `model` are null (5d); `exposure_us` from the capture info (6.6). P-1 gives `duration_s` and `stored_px` when rows are missing. |

- Written by `start_take` before the first frame, and by `finish` after the last media file is
  closed [SFF-724]. Each write reads the file when it exists, changes it, and writes it whole, under
  the lock (6.7) [SFF-724, SFF-726, SFF-786]. It keeps each member and each item that freemocap owns
  [SFF-724].
- JSON in the form of SFF-702: the members in the order of the table, integers with no fraction,
  other numbers in the shortest form.

### 6.6 The capture info JSON

`<rec>_info.json` has the members of section 13 of the format, in that order, and no other member
[SFF-800]. `start_take` writes it before the manifest. `finish` writes it again before the
manifest, with the same content [SFF-801].

| Member | 5a value | Waits for |
|---|---|---|
| `skellyfileformat`, versions, `writer`, `take_uuid` | As in 6.5. | — |
| `camera_configs` | One member for each camera, the key is `camera_key`, in order of `group_position` [SFF-800]. | — |
| `audio` | null [R5]. | 5b |
| config `camera_label` | 6.2. | 5d |
| config `user_name` | null. | 5d |
| config `key_origin` | `"provisional"` [P-5] [R8]. | 5d |
| config `device.os_name` | The friendly name of the detection (`CameraDeviceInfo.name`). | — |
| config `device.vendor_id`, `product_id` | 4 lowercase hexadecimal characters from the detection, or null. | — |
| config `device.backend` | `"media_foundation"` for the Media Foundation source; the lower-case OpenCV backend name (for example `"v4l2"`, `"avfoundation"`, `"msmf"`) for the OpenCV source [agent 22]. | — |
| config `device.os_index` | The detection index. | — |
| config `device.model`, `serial`, `port_path`, `os_device_id` | null. | 5d |
| config `requested` | `width`, `height`, `framerate` (the requested number, or `"camera_default"` for a request of -1 or 0 [D16]), `capture_format` (`"MJPG"` or `"YUYV"`), `exposure_mode` (`"auto"`, `"manual"` or `"recommend"`). | — |
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
| `capture.<id>.input_range` | The log of the camera process only [agent 22]. The format has no place for it. |
| `dead_cameras` | The manifest warning `camera_dead` [P-4] |
| The `warnings` items `auto_control`, `mixed_rate` | `controls.<name>.auto`; `nominal_rate` of each CSV. The response and the log keep them as in [cap 11.3]. |

### 6.7 Whole-file writes and the lock

- A whole-file write writes `<name>.tmp` in the same folder, forces it to disk with `os.fsync`,
  then replaces the file with `os.replace` [SFF-786].
- The lock is the file lock of the OS on `.processing.lock` [SFF-789]: on Windows `msvcrt.locking`
  with `LK_NBLCK` on byte 0, on Linux and macOS `fcntl.flock` with `LOCK_EX | LOCK_NB` [agent 15]
  [P-6]. The take level creates the empty file when it does not exist.
- The take level holds the lock for each read, change and write of the manifest and of the capture
  info [SFF-724, SFF-789, SFF-801]. It tries again every 50 ms with a blocking sleep, for at most
  `lock_timeout_s` (10 s) [agent 15].
- A lock timeout in `start_take` refuses the take (4.2). A lock timeout in `finish` leaves the
  manifest in the state `recording`, logs an error, and gives the stop response from the CSVs
  [agent 15]. Step 5c repairs such a take.

## 7. Row rules

### 7.1 A normal frame

A frame with no bit of the error mask 0x0F gives one block and one row. `flags` has:

- bit 0 (1) `gap` when `source_frame_number` is not the value of the row before plus 1 and is not
  equal to it; 0 in the first row and when this row or the row before has no
  `source_frame_number` [SFF-756];
- bit 3 (8) `repeat` when `source_frame_number` equals the value of the row before [SFF-756];
- bit 1 (2) `filled` and bit 2 (4) `encode_skip`: always 0. Step 5a copies no frame [SFF-756]. The
  encoder of step 3b falls back and loses no frame [cap 13.2, T-CAP-64]. Thus skellycam never
  skips a frame for the encoder;
- 0 in each other bit. The ring flags `DISCONTINUITY` and `DHT_INSERTED` do not go into the CSV
  [agent 30] (section 15.3).

### 7.2 A damaged frame [R3]

- A frame with a bit of the error mask 0x0F of [ring 4] in `flags` is damaged [R3]. By the order of
  [ring 5.3], only `CAPTURE_ERROR` (0x02) and `NO_SOI_EOI` (0x04) can reach the recorder: the ring
  sets `OVERSIZE` and `DECODE_ERROR` after it.
- The writer stores no block for it. The damaged bytes are not kept anywhere [R3].
- The writer writes a missing row: the flag `missing` (bit 4, 16) [P-1]; `source_frame_number`,
  `arrival_ns` and `sample_ns` of the frame; `byte_offset` and `byte_size` empty. The flags `gap` and
  `repeat` follow 7.1.
- The last good image is not repeated [R3]. Thus U5 goes.
- The next stored block gets the next block number b, so its container time follows the block
  before it (6.3) [P-2].
- The count is the `missing` value of the `# end` line [R3, P-1]. `damaged_count` of the result
  gives the count to the log.

### 7.3 A dead camera [R2]

- A camera dies during a take [D38]. The other cameras keep recording [D38].
- Its camera process stops giving frames. It calls `end` (4.3): the queued frames are written, the
  MKV is closed normally, with its index. Then the process reports and ends [cap 8.2].
- At the end of the take, the take level adds one missing row for each multi-camera frame after the
  last row of that camera, to the frame count of the take (7.6) [R2]. Each such row has only
  `frame`, `flags` (16) and `crc32`; each other field is empty [P-1].
- The manifest gets a warning `camera_dead` with the camera key, its last real frame and the
  reason [R2, P-4]. The last real frame is the position of the last row with a block (`last_block_row`)
  [agent 13].
- Thus every CSV of the take has the same number of rows again [R2]. U4 goes.

### 7.4 A hung camera and the completion of one camera's files [R4]

- A call of a camera hangs during a take [cap 6.6]. The camera process reports, then ends at once
  with `os._exit`. It does not try to finish the files [R4]. Thus U12 goes.
- The main process waits for the end of the take. Then the take level completes the files of that
  camera (`completion.py`) [R4] [agent 12]:
  1. It walks the EBML elements of the MKV from the start of the Segment data and finds the complete
     blocks [SFF-740].
  2. It reads the CSV strictly [SFF-746]. It keeps the rows up to the first row that is not
     complete or has a wrong CRC.
  3. n is the smaller of two numbers: the number of kept rows that are not missing, and the number
     of complete blocks. The pair keeps the first n blocks. It keeps the rows up to the n-th row that
     is not missing, and the missing rows that come directly after that row [SFF-795, P-1].
  4. It cuts the MKV after block n − 1 and the CSV after the last row that it keeps. It changes no
     byte before a cut and appends nothing to the MKV [SFF-794]. After a process kill, the CSV
     normally has no extra row, because a row is written only after its block (6.3).
  5. It appends a missing row for each multi-camera frame up to the frame count of the take (7.6)
     [R2, R4].
  6. It appends `# repair cut_bytes=<n> media_cut_bytes=<m> repair_writer=<writer>`, then the
     `# end` line [SFF-795]. A reader then reports the pair as `repaired`. A repaired camera file
     needs no Cues [SFF-794].
- How the main process knows the frame count of the take: the CSVs of the other cameras (7.6). It
  does not need the hung process.
- A write error (5.4), a writer that did not finish (4.3), and a camera process that ended with no
  result use the same completion.
- The completion runs during the take, in the app that records it. The user is not asked: P-3
  makes this a rule of the format, apart from the repair of SFF-793 [R4]. Step 5c reuses the steps
  1 to 4 for its repair.
- The manifest gets the warning `camera_dead` with the reason "hang" or the error text [P-4].

### 7.5 A camera that stalled or had a write error

The camera that ended the take (5.3, 5.4) stops at the frame that it could not write. The other
cameras record to the last frame of the take. At the end, the take level gives the stalled camera
missing rows to the frame count of the take (7.6). After a write error, it uses the completion of
7.4.

### 7.6 Equal row counts

- Each CSV of a finished take has the same number of rows [SFF-754] [R2].
- The frame count of the take is the largest number of kept rows of a CSV of the take, after the
  reads of 8.1 [agent 11]. Reason: under the lockstep gate, each camera that records to the end has
  a row for each multi-camera frame of the take [cap 5.2].
- The take level gives each other camera missing rows up to that count (7.3, 7.4, 7.5).
- When all cameras died, the frame count is the largest count of the dead cameras.

### 7.7 Rotation

- The frames stay in sensor orientation [SFF-735]. The header holds `display_rotation` [SFF-751].
- The container holds no rotation element [SFF-735]. VLC 3.0.24 honours no rotation flag in MKV
  [M `research/skellycam_recording/docs/spec_v0_revival_tracking_sidecars_20261113.md`].
- A setting change is refused during a take [D36]. Thus the rotation does not change in a take.

## 8. The end of a take

### 8.1 Order of the steps

1. The stop request sets the last frame of the take in the orchestrator, as today
   (`last_recording_frame_number`). Each live camera records to that frame.
2. Each live camera process calls `end` and sends its `CameraTakeResult` (4.3).
3. The main process waits for one result or the end of the process of each camera, at most the
   stall limit after step 1 [agent 25]. A camera with no result after that limit is ended with
   `terminate` and joined. Its result is `None`.
4. `Take.finish`:
   1. It reads each CSV strictly [SFF-746]. It finds the frame count of the take (7.6).
   2. It completes each camera with a result `None` or an error, as in 7.4.
   3. It appends the missing rows of each dead or stalled camera (7.3, 7.5).
   4. It appends the `# end` line to each CSV, with the counts of its rows [SFF-758]. Then it forces
      each CSV to disk.
   5. It writes the capture info JSON again (6.6) [SFF-801].
   6. It writes the manifest last: `state` `"finished"`, the warnings, the summary [SFF-724,
      SFF-728].
   7. It computes the stop response fields from the CSVs (8.2).
5. The camera processes stay. A dead camera process has ended [cap 8.2].

The manifest is written last. Thus `state` `"finished"` means that every file of the take is
finished [SFF-724].

### 8.2 The stop response (R5)

`StopRecordingResponse` keeps each field [R5]. Each field comes from the CSVs of the take
[agent 14]. A missing row has no time and is left out of each statistic, as the NaN values are
left out today:

| Field | Source in 5a |
|---|---|
| `recording_name` | `<rec>`. |
| `recording_path` | The take folder. |
| `number_of_cameras` | `group_size`. |
| `number_of_frames` | The frame count of the take (7.6). |
| `total_duration_sec` | `duration_s` of the manifest summary [SFF-728, P-1]. |
| `mean_framerate` | The mean of the frame rate of each multi-camera frame k ≥ 1. The rate of frame k is the mean over the cameras of 1 / (`arrival_ns`(k) − `arrival_ns`(k − 1)) in s, for each camera with both rows not missing. Rounded to 2 decimals, as today. |
| `mean_inter_camera_sync_ms` | The mean of the range of frame k: the largest minus the smallest `arrival_ns` of the cameras with a row that is not missing, in ms. Rounded to 2 decimals. |
| `framerate_stats` | Median, mean, standard deviation, min and max of the rates of `mean_framerate`. |
| `frame_duration_stats` | The same of the mean frame duration of each frame k ≥ 1, in ms. |
| `inter_camera_grab_range_ms_stats` | The same of the ranges of `mean_inter_camera_sync_ms`. |

Today these values come from the midpoints of the grab stamps of the old frame record. From step 3a,
both grab stamps hold `arrival_ns` [cap 5.4]. Thus the meaning stays the same.

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

## 9. When the app is killed during a take (before 5c)

| File | State after a kill |
|---|---|
| Each MKV | Unfinished: no index, the last open cluster can be cut [SFF-740]. Each block before the block that the muxer held is complete. |
| Each CSV | Unfinished: no footer. Each row points to a complete block [6.3]. The last line can be torn on an OS crash [SFF-746]. |
| The manifest | `state` `"recording"` [SFF-724]. A `.tmp` file can stay after a kill during a whole-file write [SFF-790]. |
| The capture info | The version of the take start. |

Frames lost per camera: the frames in the queue, plus the block that the muxer held, plus the rows
that wait for it (6.3). T-REC-KILL measures it (section 11).

At its next start, the app does nothing with an unfinished take. It does not scan for unfinished
takes, it does not ask the question of SFF-793, and it changes no file. The manifest state
`recording` marks the take [SFF-724]. The playback list leaves out each take folder of the new
format (section 10) [R9]. Step 5c adds the scan, the question and the repair [R1].

## 10. Connection to the shared loop (after step 3a)

The module stays apart from the loop until step 3a of phase 3 is joined [R10]. Then one connection
commit, with the tests T-REC-38 to T-REC-45, does these steps:

1. **Hand-over point.** In step 6 of [cap 5.1], the loop calls `give` with a `RecorderFrame` for each
   recorded frame, before the JPEG ring write [ring 5.3]. The fields come from `CapturedFrame` and
   from the capture check [cap 4.2, ring 5.2].
2. **Camera bytes.** `payload` is the object that the source gave, before the DHT insertion of
   [ring 5.2] step 6 [SFF-734] [agent 21]. Only when a DHT was inserted are the recorder object and
   the ring object different. No test camera sends such a frame [ring 5.2].
3. **Start and end.** The recording-info message to the camera processes carries the
   `CameraTakeSpec`. The camera process calls `start` when it gets it, and `end` after the last frame
   of the take. The finished message carries the `CameraTakeResult`.
4. **The interim decode goes** [D9]: the decode of [cap 5.5] for the old recorder, and the BGR
   conversion of [cap 13.2] for the old recorder. A camera with a BGR ring keeps one decode, in the
   decode stage on its own thread [ring 8.2 to 8.4]. Item 5 of [cap 17.2] then no longer applies.
5. **U5 goes.** A damaged frame gives a missing row (7.2). The old recorder is gone.
6. **U4 goes.** A dead camera gives missing rows to the end of the take (7.3). No recording info JSON,
   no `dead_cameras` list.
7. **U12 goes.** On a hang during a take, the camera process reports, then ends at once with
   `os._exit` (7.4).
8. **The stall and the write error.** The loop catches `RecorderStalled` and `RecorderWriteError`,
   reports them, and the main process ends the take (5.3, 5.4).
9. **The end of a take.** `CameraGroup.stop_recording` waits for the results with the limit of 8.1
   and calls `Take.finish`. The stop endpoint builds `StopRecordingResponse` from `TakeSummary`
   (8.2). The old finaliser goes (8.3).
10. **The start of a take.** The start endpoint calls `start_take`. A `<rec>` that breaks SFF-715 gets
    HTTP 422. A take folder that holds files, or a lock timeout, gets HTTP 409 [agent 16]. A start
    request with a microphone follows question Q1.
11. **Status.** The camera status gets `recorder`: `{"queue_depth", "queue_high_water",
    "give_wait_count", "give_wait_ms_max", "state"}` [P §6] [agent 31]. Its display in the UI is
    open (section 15.2).
12. **Playback list.** `list_recordings` leaves out a folder whose `recording_manifest.json` has
    `"skellyfileformat": "recording_manifest"` [R9] [agent 23]. Old recordings stay in the list.
13. **Deletions** of 8.3, after a search for each caller.

The tests of `windows-capture.md` that change are in section 14.

## 11. The measurements of R11

Each runs on synthetic JPEG frames with no camera [R11]. The synthetic source is a thread that makes
frames on an absolute schedule and puts them in a waiting place, as the fake source of [cap 4.4]
does. The frames are JPEGs of a moving test pattern from `cv2.imencode` at quality 90: 1280x720
(about 60 kB) and 1920x1080 (about 200 kB) [agent 27]. Each benchmark writes a JSON summary to the
path in `SKELLYCAM_BENCH_OUT`, outside the repository. An evidence entry reports the summary with
the tool versions (Python 3.13.18, PyAV 19.0.2) and the machine. The user gets the results before the
two numbers are fixed [R11].

| ID | Method | Recorded | Kind | Decides |
|---|---|---|---|---|
| T-REC-STALL | 1 and 4 camera processes, 720p30 and 1080p60. The MKV file object of one writer blocks one time for 0.5, 2, 10 and 15 s at frame 300. Each run is 60 s. Plan: "Once to a slow USB stick" — an optional run by the user on a USB stick, with no injected stall [P §7]. | Queue high-water (frames, s); `give` waits (count, longest); frames replaced in the source; rows of each camera; capture lateness of the other camera processes (arrival against schedule, p50, p99, max). | Benchmark with pass parts: for 0.5 s and 2 s, no `give` wait and no lost frame; for 10 s, the queue fills, `give` waits about 7 s, no lost frame, equal rows; for 15 s, the take ends with `take_error`, every file is finished, equal rows. | The queue size (`QUEUE_SECONDS`) and the stall limit [R11]. |
| T-REC-KILL | 1 camera process, 720p30. 20 kills during normal writing and 20 kills with a full queue (a blocked writer), at random frames; `TerminateProcess` on Windows, `SIGKILL` on Linux and macOS. | Frames given minus rows written, against the queue depth at the kill; torn bytes. | Process test with pass parts: each row has a correct CRC and its block bytes equal the frame given; blocks − non-missing rows is 0 or 1; PyAV reads each complete block. | The cost of a larger queue on a kill; it confirms the file-object writer [agent 6]. |
| T-REC-FSYNC | 16 camera processes at 1080p60, fsync once per second on and off, 3 runs of 60 s each, and one run of 10 min with fsync on. | Per-frame write time (p50, p99, p99.9, max); fsync time (p50, max); queue high-water; capture lateness; CPU of each process. | Benchmark, no pass value. | Whether SFF-788 (once per second) stays; input for the queue size and the stall limit [R11]. |
| T-REC-GIL | 4 camera processes at 720p30 and 1 at 720p60, 10 min, writer on and off [P §7]. In each process: the source thread, the loop thread and the writer thread. | Arrival lateness against the schedule, interval jitter, loop step time (p50, p99, max), writer on against off. | Benchmark, no pass value. | Whether the writer thread delays capture [R11]. |

The plan names T-REC-GIL with cameras [P §7]. R11 moves it to synthetic frames. The mix of 30 and
60 fps is allowed here, because these processes have no gate. In the app, D18 refuses that mix. The
plan test T-REC-MF-DEFER needs a camera. It is not in R11 and waits for the connection (section
15.1).

## 12. Tests

### 12.1 Kinds, markers and parity

- **unit**: in one process, with synthetic frames and the module only. CI runs them.
- **process**: spawns or kills processes. CI runs them. Marker `recorder_slow` for a test that runs
  longer than 10 s [agent 27].
- **benchmark**: section 11. Marker `recorder_bench`. They run only with `SKELLYCAM_BENCH=1`, on the
  machines of the user, because the shared CI runners give no stable times [agent 27]. The pass parts
  of T-REC-STALL and T-REC-KILL also run in CI in a short form (5 kills, stalls of 0.5 and 15 s, with
  `QUEUE_SECONDS` and the stall limit scaled down by 10).
- **connection**: T-REC-38 to T-REC-45. They come with the connection commit and use the fake source
  of [cap 16.1].
- Parity: each unit, process and connection test runs on Windows, Linux and macOS. The kill uses
  `TerminateProcess` on Windows and `SIGKILL` elsewhere; the lock uses `msvcrt` on Windows and
  `fcntl` elsewhere (6.7). No test is for one OS only. `test.yml` has runners for the three systems.
  Its trigger is open work (question Q3). The benchmarks run on Windows, and on Linux and macOS when
  the user has the machine.

### 12.2 Test list

Each test of the kinds unit and process uses at least two cameras unless it says one.

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-REC-01 | unit | Start a take with two cameras, give 100 frames to each, end it. List the take folder. | Exactly the files and folders of 6.1 with their exact names. No MP4, no WAV, no `timestamps/` folder, no other CSV, no statistics file, no recording info JSON, no `synchronized_videos_README.md` [SFF-716, SFF-719, SFF-722, R5]. |
| T-REC-02 | unit | `start_take` with each bad `<rec>` of SFF-715 (empty, 129 bytes, `.`, each of `/ \ : * ? " < > \|`, a control character, a leading space, `CON`, `com1`, `LPT9`), a folder that holds a file, a rate of 1001/1, a rate of 0/1 and 2^20 + 1, `capture_format` H.264. | Each raises `ValueError`; no file or folder is created or changed [SFF-715, SFF-719, SFF-736, SFF-750, SFF-734]. |
| T-REC-03 | unit | Cameras with `camera_id` `0a1b` and `ff00`. | `camera_key` and `camera_label` follow 6.2; the label starts with `camera_id` and has the form of SFF-753; the file names use the label; the manifest `cameras` items are in order of `group_position` with the exact `video` and `timing` paths; `key_origin` is `"provisional"` [R8, SFF-720, SFF-723, P-5]. |
| T-REC-04 | unit | Takes at 30/1, 30000/1001 and 60/1, 50 frames. Walk the EBML elements of each MKV with the test's own parser. | DocType `matroska`; one track, `V_MJPEG`, number below 128; each frame one `SimpleBlock` with the keyframe flag and no lacing; TimestampScale 1,000,000; block b at ⌊(2b·den·1000 + num)/(2·num)⌋ ms; `DefaultDuration` ⌊10^9·den/num⌋ (33,366,666 for 30000/1001); no `Projection`, no other rotation element, no other track [SFF-732, SFF-733, SFF-735, SFF-736, P-2]. |
| T-REC-05 | unit | Give JPEGs with no DHT, with bytes after EOI, with APP0, APP1 (EXIF) and APP14 segments, and of different sizes. | The payload of each block is byte-equal to the frame given (SHA-256 of each) [SFF-734, SFF-737]. |
| T-REC-06 | unit | Give 1,000 frames to a writer whose thread is held, then release it. Track the queue items and the allocations with `tracemalloc`. | Each queue item holds the same object as the frame given (`is`); no allocation of the payload size in `give` [ring 5.7, R10]. |
| T-REC-07 | unit | Read each CSV header of a take. | Each key of 6.4 in its order with its value; the take keys are equal in each CSV; `clock` is the value of the OS; `audio_count` 0; UTF-8, no byte order mark, LF; the column line of section 8 of the format [SFF-700, SFF-707, SFF-710, SFF-742, SFF-743, SFF-749, SFF-772, SFF-774]. |
| T-REC-08 | unit | Give frames with known arrival and sample times, and frames with `NO_SAMPLE_NS`. | `frame` is 0, 1, 2 …; the times are relative to `take_start_host_ns`; an empty `sample_ns` for `NO_SAMPLE_NS`; each integer in the form of SFF-701; no quote; each CRC is correct [SFF-701, SFF-704, SFF-741, SFF-744, SFF-754, SFF-755]. |
| T-REC-09 | unit | `source_frame_number` sequences: +1, +3, equal, and frames with `DISCONTINUITY` and `DHT_INSERTED`. | `gap` and `repeat` as in 7.1; 0 in the first row; `filled` and `encode_skip` 0; the two ring flags change nothing [SFF-756]. |
| T-REC-10 | unit | During a take, after each `give`, read the CSV and the MKV that are on disk. After the end, read them again. | Each complete row points at a byte range of the MKV that equals the frame given; the values do not change after the close; the last row also [SFF-757 (DT5), agent 7]. |
| T-REC-11 | unit | End a take with one gap, two damaged frames and a dead camera. | Each CSV ends with `# end` with the right `rows`, `gaps`, `filled`, `encode_skips` and `missing`; no `# fit` line [SFF-745, SFF-758, P-1, R1]. |
| T-REC-12 | unit | Give frames 0 to 99; frames 20 and 21 have `CAPTURE_ERROR`, frame 50 has `NO_SOI_EOI`; repeat with each bit of 0x0F. | Rows 20, 21 and 50 are missing rows with their times and empty byte fields; the MKV has 97 blocks; the damaged bytes are not in the MKV; block times stay contiguous; `missing=3` [R3, P-1, P-2]. |
| T-REC-13 | unit | Spy on the writes of the CSV file object. | One `write` call for each row, with its LF; the file on disk holds only complete lines after each call [SFF-744, SFF-787]. |
| T-REC-14 | unit | Read the manifest after `start_take`, during the take and after the end. | The members of SFF-723 in order; `state` `recording`, then `finished`; `files` with the SHA-256 of the capture info; the summary nulls of SFF-728 at the start and the values at the end; `camera_gap` for the camera with a gap; `privacy` of 6.5; the JSON form of SFF-702 [SFF-702, SFF-723, SFF-724, SFF-727, SFF-728, SFF-881, SFF-882]. |
| T-REC-15 | unit | Trace the file actions of `start_take` and `finish`. Put an unknown member and a freemocap `files` item in the manifest during the take. | Each whole-file write is `.tmp`, fsync, one rename, inside lock and unlock; the read comes after the lock; the unknown member and the freemocap item stay [SFF-724, SFF-726, SFF-786, SFF-789, SFF-801]. |
| T-REC-16 | process | A second process holds `.processing.lock` with the lock of 6.7. Case 1: it releases after 2 s. Case 2: it holds 15 s. | Case 1: `finish` waits and then writes. Case 2: `start_take` raises `TimeoutError` with no file written; at the end of a take, the manifest stays `recording` and an error is logged [SFF-789, P-6]. |
| T-REC-17 | unit | Read the capture info after the start and after the end. | The members of section 13 of the format in order and no other; keys in order of `group_position`; the values of 6.6; null for the 5d fields; no `rotation`; written at the start and the end [SFF-800, SFF-801, SFF-802, P-5]. |
| T-REC-18 | unit | Inject the two clocks of `start_take`. | The host clock is read first, the UTC clock at once after it, both before the first frame; `utc_offset_min` is the local offset [SFF-774]. |
| T-REC-19 | unit | Hold the writer thread. Give frames until the queue is full, then one more from a second thread. Release the writer. | The extra `give` waits; while it waits, the process uses under 2 % of one core; it returns when space comes; each frame is in the CSV; the counts of 5.2 are right [P §6, ring 8.10]. |
| T-REC-20 | unit | Queue sizes at 30/1, 30000/1001 and 60/1. | 90, 90 and 180 frames (5.1) [agent 4]. |
| T-REC-21 | unit | Hold the writer for longer than the stall limit (scaled down in the test). | `give` raises `RecorderStalled` at the limit (±10 %); `end` returns within the limit; `finish` with `ended_by_error` gives `take_error`, `state` `finished`, equal rows; a new take starts in the same process [P §6]. |
| T-REC-22 | unit | The MKV file object of one camera raises `OSError(ENOSPC)` at frame 50. | The next `give` raises `RecorderWriteError`; the take level completes that camera (7.4); the other camera is finished; the manifest has `take_error` [P §6, P-3, P-4]. |
| T-REC-23 | unit | Camera B ends at frame 300 of a take of 600 frames (`end` called early, as a dead camera). | B's CSV has 600 rows; rows 300 to 599 are missing rows with only `frame`, `flags` and `crc32`; B's MKV has 300 blocks and a normal end; `missing=300`; the manifest has `camera_dead` with last real frame 299; the stop statistics leave out the missing rows [R2, P-1, P-4]. |
| T-REC-24 | process | Camera B writes in its own process. It ends with `os._exit` at 20 kill points, also between a `mux` and its row write and during a row write. The take ends 100 frames later. | B's MKV is cut after its last block with a row; the CSV keeps each good row; missing rows reach the frame count; `# repair` then `# end`; each row's bytes equal the frame given; PyAV reads each block; `camera_dead` with reason "hang" [R4, SFF-794, SFF-795, P-3]. |
| T-REC-25 | unit | Mixes: all live; one dead at 10; one hung at 20 and one stalled at 30; all dead. | Equal rows in every case; the frame count is the largest count of kept rows (7.6) [R2, SFF-754]. |
| T-REC-26 | unit | Trace the end of a take. | The order of 8.1: each MKV closed, then the CSV reads, completions, missing rows, footers, the capture info, the manifest last [SFF-724]. |
| T-REC-27 | unit | CSVs with known arrival times, also missing rows, through `stop_stats`. | Each field of 8.2 equals the value computed by hand to 1e-9 [R5]. |
| T-REC-28 | unit | Display rotations 0, 90, 180, 270; then a frame with a rotation that differs from the spec. | The header value; no rotation element; the bytes unrotated; the odd frame raises `ValueError` [SFF-735, SFF-751, agent 33]. |
| T-REC-29 | unit | Inject the clock of the writer thread. | One fsync of the MKV and one of the CSV for each second with a row, on the writer thread only; one fsync of each at `end` [SFF-788, agent 9]. |
| T-REC-30 | unit | A camera dies before its first frame. | Its CSV holds only missing rows; its MKV has no block and PyAV opens it; `stored_px` is null for it [P-1]. |
| T-REC-31 | unit | Open each finished MKV of T-REC-12 and T-REC-23 with PyAV 19.0.2 and with OpenCV 5.1.0 (`CAP_PROP_FRAME_COUNT`, 11 `POS_FRAMES` seeks). | The packet count and the OpenCV count equal the blocks; each seek gives the expected block [M `RU/results/crash_resilience/gapfill/GF02_container_matrix.md`, P-2]. |
| T-REC-32 | unit | Call `give` before `start`, after `end`; call `end` twice. | Each raises `RuntimeError` (4.3). |
| T-REC-33 | unit | Search the module for PyAV calls. | Only the calls of 6.3; no `add_stream_from_template`, no `add_stream(`; the container options hold `flush_packets` `"1"` [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1]. |
| T-REC-34 | unit | Open the stream with the keyword form of 6.3 and with the positional form of the evidence. | Both give byte-equal files for the same frames. |
| T-REC-35 | process | Kill a writer process during a take; then call `start_take` on another folder; then list the playback recordings. | The killed take keeps every byte (SHA-256 before and after); the new take works; the killed take is not in the list (section 9). |
| T-REC-36 | unit | A take at 1080p with frames of 600 kB at 60/1, 30 s, in one process. | No `give` wait on a free disk; every frame in the CSV (a sanity check, not a measurement). |
| T-REC-37 | unit | Run the conformance subset of 12.3. | Only the expected results of 12.3. |
| T-REC-STALL | benchmark | Section 11. | Section 11. |
| T-REC-KILL | process | Section 11. | Section 11. |
| T-REC-FSYNC | benchmark | Section 11. | No pass value. |
| T-REC-GIL | benchmark | Section 11. | No pass value. |
| T-REC-38 | connection | Three fake cameras in the shared loop at 30 fps; the writer of one is held 2 s. | All three loops wait; after it, each camera's next row has `gap`; for each camera the sum of the gaps of `source_frame_number` equals the increase of `replaced_count` [D26, D27]; equal rows. |
| T-REC-39 | connection | Record with and without a BGR ring; count `cv2.imdecode` calls on the loop thread and on the decode thread. | No decode for the recorder; one decode per frame on the decode thread only when a BGR ring exists [D9, ring 8.2]. |
| T-REC-40 | connection | The fake delivers a cut-off JPEG during a take. | A missing row; no block; the previous image is not stored again; no decode call [R3]. |
| T-REC-41 | connection | Three fakes record; one gives device removed at frame 300. | That camera is `dead`; its MKV is closed normally; every CSV has the same rows; `camera_dead` in the manifest; no recording info JSON [R2, D38]. |
| T-REC-42 | connection | A bounded call of one fake hangs during a take. | The failure is reported; the process ends within 1 s of the report; the take level completes its files at the end; the others record to the stop [R4]. |
| T-REC-43 | connection | Start and stop a take over HTTP with fake sources (not port 53117). | The response has each field of `StopRecordingResponse` with the values of 8.2 [R5]. |
| T-REC-44 | connection | A start request with `mic_device_index` 0. | The behaviour of the answer to Q1. |
| T-REC-45 | connection | A fake sends a JPEG with no DHT. | The ring slot holds the JPEG with the DHT inserted; the MKV block holds the bytes of the fake [SFF-734, agent 21]. |

### 12.3 Conformance check against skellyfileformat

- skellyfileformat has runnable conformance tests in `tests/conformance/`. They reach a program
  through a test adapter. The Python adapter exposes `TakeWriter` with `write_frame`, `write_audio`,
  `add_warning` and `close`, `repair_take`, `release_check`, the reader `read_folder` and the detail
  functions (`spec/conformance.md`, "The test adapter"; `tests/conformance/INTERFACE_NOTES_capture.md`).
  The environment variable `SKELLYFILEFORMAT_ADAPTER` names the module.
- Step 5a adds `skellycam/tests/take_recorder/sff_adapter.py` [agent 28]. It exposes only
  `TakeWriter` on top of `start_take`, `CameraTakeWriter` and `finish`, in one process. It has no
  `write_audio` (5b), no `repair_take` (5c), no reader (phase 6) and no `release_check` (5b).
- T-REC-37 checks out skellyfileformat at commit `d67679ada704caf55c64c2e279081d317205f354` next to
  the repository (`../skellyfileformat`) or in CI, and runs
  `pytest -m stage1a tests/conformance/test_s04_05_folder_manifest.py tests/conformance/test_s06_camera.py tests/conformance/test_s07_10_sidecars_audio.py tests/conformance/test_s13_15_info_calibration.py`.
- Expected results. The first run writes the list of each test function and its result into
  `skellycam/tests/take_recorder/conformance_expected.json`. After that, the test fails when a
  result differs from the list. Each expected failure must have one of these reasons:

  | Reason | Example tests |
  |---|---|
  | The test uses audio (5b). | SFT-711 `two_cameras`, SFT-715, SFT-720 to SFT-722 |
  | The test reads with `read_folder` (phase 6). | SFT-717, SFT-713 |
  | The test expects fit lines (5b). | each check of a finished sidecar that needs `# fit` |
  | The test needs `repair_take` (5c). | SFT-730, SFT-733 |
  | The test sends raw YUYV frames or an encoder failure; the recorder takes JPEG only. | SFT-717 `encoder_failure` |
  | The test expects `key_origin` `computed` or the label of SFF-720 (5d). | SFT-705, SFT-735 |
  | The test does not know a proposal of section 13 that the user accepted. | each test that P-1 to P-6 change |

  Each other failure is a defect of the recorder.
- The tests that should pass in 5a include SFT-711 `four_rotations` and `rate_30000_1001` and
  SFT-712 for the JPEG bytes [NV until the run]. SFT-708 writes audio, so it waits for 5b.

### 12.4 Decision to tests

| Decision | Tests |
|---|---|
| R1 | Section 2 (the order of the steps); T-REC-11 (no fit lines in 5a); T-REC-38 to T-REC-42 (U4, U5, U12 and the interim decode go) |
| R2 | T-REC-23, T-REC-25, T-REC-41 |
| R3 | T-REC-12, T-REC-40 |
| R4 | T-REC-24, T-REC-42 |
| R5 | T-REC-01, T-REC-27, T-REC-43 |
| R6 | No test: section 13 holds the proposals. |
| R7 | No test: the evidence stays and is cited. |
| R8 | T-REC-03, T-REC-17 |
| R9 | T-REC-35 (the list leaves out new takes) |
| R10 | T-REC-06; each unit test runs with no camera; T-REC-38 to T-REC-45 come only with the connection |
| R11 | T-REC-STALL, T-REC-KILL, T-REC-FSYNC, T-REC-GIL |
| R12 | No test: the order of the work. |

### 12.5 Format rules to tests

| Rules | Tests | Note |
|---|---|---|
| SFF-700, 701, 702, 703, 704 | T-REC-07, 08, 14 | |
| SFF-707, 710, 712 | T-REC-07, 14, 17 | |
| SFF-715, 716, 717, 719, 722 | T-REC-01, 02 | SFF-717: no rename call exists. |
| SFF-720, 752, 753 | T-REC-03 | 6.2 and P-5 until 5d [R8]. |
| SFF-723, 724, 726, 727, 728 | T-REC-14, 15, 23 | P-4 adds codes. |
| SFF-732 to 737 | T-REC-04, 05, 28, 31, 33 | P-2 for SFF-736. |
| SFF-741 to 745, 749, 750, 751, 754 to 758 | T-REC-07 to 13, 23, 30 | P-1. SFF-757 is provisional (DT5). |
| SFF-772, 774 | T-REC-07, 18 | SFF-773 provisional. |
| SFF-786, 787, 788, 789 | T-REC-13, 15, 16, 29 | SFF-788 provisional; T-REC-FSYNC. |
| SFF-794, 795 (the completion only) | T-REC-22, 24 | P-3. |
| SFF-800, 801, 802 | T-REC-17 | SFF-802 partly until 5d. |
| SFF-881, 882 | T-REC-14 | |
| SFF-884 | No test: the module writes JSON and CSV only. | |
| SFF-760 to 771, 775 to 779 | None in 5a | Audio and fit: 5b [R1]. |
| SFF-793, 796 to 798 | None in 5a | Repair: 5c [R1]. |
| SFF-708, 709, 711, 713, 714, 718, 721, 729 to 731, 738 to 740, 746 to 748, 753, 759, 780 to 785, 790 to 792, 799, 803, 864 to 893 | None in 5a | Reader rules: phase 6. |
| SFF-725, 804 to 863 | None | freemocap, Blender addon, skellysync. |

### 12.6 Counts

| Kind | Tests |
|---|---|
| unit | 34 (T-REC-01 to T-REC-15, T-REC-17 to T-REC-23, T-REC-25 to T-REC-34, T-REC-36, T-REC-37) |
| process | 4 (T-REC-16, T-REC-24, T-REC-35, T-REC-KILL) |
| benchmark | 3 (T-REC-STALL, T-REC-FSYNC, T-REC-GIL) |
| connection | 8 (T-REC-38 to T-REC-45) |
| All | 49 |

T-REC-STALL and T-REC-KILL also have pass parts (section 11).

## 13. Proposed changes to skellyfileformat

The recorder needs these rules. This spec does not edit skellyfileformat. Each change is a local
commit there, pushed only on the word of the user [R6]. The text is the proposed rule text.

**P-1: missing rows** (R2, R3, R4). Touches SFF-740, SFF-754, SFF-756, SFF-758, SFF-759, SFF-728,
SFF-781, SFF-783, SFF-795 and the column table of section 8.

> **SFF-756** (add): Bit 4 (16): `missing`, the writer stored no frame for this row. A capture
> writer writes it for a frame with a capture error, and for each multi-camera frame after the last
> frame of a camera that stopped during the take. In a `missing` row, `byte_offset` and `byte_size`
> are empty. `source_frame_number`, `arrival_ns` and `sample_ns` hold the values of the frame that
> had the error, or are empty when the camera gave no frame.
>
> **SFF-754** (replace the first sentence): There is one row for each multi-camera frame of the
> take, in position order. A row without the flag `missing` has one block in the camera file. A row
> with the flag `missing` has no block.
>
> **Section 8 columns** (change): `arrival_ns`: "The arrival time (relative), or empty in a
> `missing` row".
>
> **SFF-758** (change): `# end rows=<R> gaps=<G> filled=<F> encode_skips=<E> missing=<M>`.
> `missing` is the number of rows with the flag `missing`.
>
> **SFF-759** (replace the first sentence): The number of rows without the flag `missing` of a
> finished or a repaired video sidecar is the number of blocks of its camera file.
>
> **SFF-740** (change): Row k of the sidecar that is not `missing` belongs to the j-th complete block
> of the camera file, where j is the number of rows before row k that are not `missing`. A `missing`
> row is usable when it is complete and its CRC is correct. It has no block.
>
> **SFF-795** (add): In this rule, "the number of complete blocks" counts the rows that are not
> `missing`. The repair keeps the `missing` rows that come before the cut.
>
> **SFF-781** (add): A `missing` row has no player time. In the strict player time of SFF-782, the
> reader skips it.
>
> **SFF-885** (add): `rows` counts the `missing` rows. A `records` item of a `missing` row holds the
> values of the row, and `player_ns` is null.
>
> **SFF-783** (add): At a take time in a `missing` row, a player shows the last frame before it.
>
> **SFF-728** (change): `duration_s` uses the largest `arrival_ns` of the last row that holds an
> `arrival_ns` of each video sidecar. `stored_px` is null when the camera file has no block.

**P-2: container time of a block.** Touches SFF-736.

> **SFF-736** (change): The container timestamp of the b-th block of the file, counted from 0, is
> ⌊(2 × b × `den` × 1000 + `num`) / (2 × `num`)⌋ ms. b counts the blocks, not the rows: a `missing`
> row (SFF-756) leaves no hole in the container times.

**P-3: completion of a camera pair during a take** (R2, R4). New requirement after SFF-798.

> **SFF-894** (writer): When the process that writes a camera pair ends during a take with no normal
> end of its files (a hang, a write error), the capture writer completes that pair at the end of the
> same take, in the same run of the program. It does steps 1 to 3 of SFF-793 for that pair only: it
> cuts the camera file and the sidecar as SFF-795 gives, and appends no byte to the camera file. Then
> it appends a `missing` row (SFF-756) for each multi-camera frame up to the number of rows of the
> other sidecars of the take, the `# repair` line and the `# end` line. This is not the repair of
> SFF-793: the program does not ask the user. A reader reports the pair as `repaired`. When the
> process ended normally before the end of the take (a camera that stopped), the capture writer only
> appends the `missing` rows and the `# end` line to its sidecar.

**P-4: two warning codes.** Touches SFF-727.

> **SFF-727** (add): skellycam also writes `camera_dead` (a camera stopped during the take; the
> sidecar holds `missing` rows to the end of the take) and `take_error` (an error ended the take).
> The `detail` of `camera_dead` is `last_frame=<p> reason=<text>`, where p is the position of the
> last row with a block, or `none`. The `detail` of `take_error` is the error text. `camera_key` of
> `take_error` is the camera of the error, or null.

**P-5: a provisional key.** Touches SFF-752, SFF-803 and the camera config table of section 13.

> **Section 13, `key_origin`** (add a value): `"provisional"`: a capture writer that cannot read the
> identity of SFF-752 made the key from its own camera identifier. The key is not stable across
> computers or sessions. A program does not remember it.
>
> **SFF-803** (change): a reader checks that `key_origin` is one of its four values.

**P-6: the lock on each OS.** Touches SFF-789.

> **SFF-789** (add): On Windows, the lock is `LockFileEx` with `LOCKFILE_EXCLUSIVE_LOCK` on byte 0
> for 1 byte (Python: `msvcrt.locking` with `LK_NBLCK`). On Linux and macOS, it is `flock` with
> `LOCK_EX` on the whole file. Each program uses this form, because a `flock` lock and an `fcntl`
> record lock do not see each other on Linux.

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
| 5.4 | "The frame rate given to the old recorder is the mode rate, not the median of the frame intervals [agent 9]." | "The nominal rate of the recorder is the mode rate ([`recorder.md`](recorder.md) 6.4)." |
| 5.4 | "`sample_ns` goes into the slot header, and nothing uses it yet [D28]. Phase 5 decides." | "`sample_ns` goes into the slot header and into the CSV of the recorder [D28]." |
| 5.5 | The whole section. | "The decode of a JPEG runs only for a BGR ring, in the decode stage [ring 8.2 to 8.4]." Title: "Decode for the BGR ring". |
| 5.7 | The whole section (U4). | Delete. A dead camera: [`recorder.md`](recorder.md) 7.3. |
| 6.6 | "On a hang during a recording, the camera process reports, then tries to finish the recording files of that camera for at most 5 s. Then it ends hard [U12]. The hung call is on a worker thread, so the loop thread can still close the files." and "This is an interim rule of phase 3. The recorder of phase 5 writes files that survive a hard stop. Then the rule goes [U12]." | "On a hang during a recording, the camera process reports, then ends at once. The main process completes its files ([`recorder.md`](recorder.md) 7.4) [R4]." |
| 8.2 | "The process of a dead camera reports, finishes its recording files [D38], closes the source with the bounded steps of 6.9 and ends. Thus a dead process lives until its files are finished and its close steps end. After a hang during a recording, the file finish has a limit of 5 s (U12), and then the process ends hard." | "The process of a dead camera ends its camera writer ([`recorder.md`](recorder.md) 7.3) [D38], reports, closes the source with the bounded steps of 6.9 and ends. After a hang, the process ends at once [R4]." |
| 11.3 | "The recording info records that the control was in auto for this take (11.6) [D37]." | "The capture info records it in `controls.<name>.auto` [D37]." |
| 11.5 | "White balance is read only. Its value and auto flag go to the recording info [D43]." and "Step 3c reads it and writes it to the recording info [D44]." | "… go to the capture info (step 5d) …" in both sentences. |
| 11.6 | The whole section. | "The capture data goes to the capture info JSON and the manifest ([`recorder.md`](recorder.md) 6.6)." |
| 13.2 | "The old recorder takes BGR in phase 3 (D9). … A frame is never converted two times [agent 36]." | "The recorder takes the encoded JPEG. A BGR conversion runs only for a BGR ring [ring 8.7]." |
| 13.3 | "The range goes into the recording info (11.6) [notes: Input range]." | "The camera process logs the range ([`recorder.md`](recorder.md) 6.6)." |
| 17.2 | Items 5 and 12. | Item 5: "Resolved by step 5a." Item 12: delete. |
| 16.2 | T-CAP-07, T-CAP-09, T-CAP-10, T-CAP-34, T-CAP-35, T-CAP-39, T-CAP-58, T-CAP-65, T-CAP-67, T-CAP-74, T-CAP-85 | T-CAP-07: the CSV time is the recorder CSV `arrival_ns`. T-CAP-09: replaced by T-REC-39. T-CAP-10: replaced by T-REC-40. T-CAP-34: "the capture info has `controls.exposure_us.auto` true". T-CAP-35: replaced by T-REC-41. T-CAP-39: drop the CSV column part; keep the refusal of a wrong camera ID. T-CAP-58: "the manifest has `camera_dead` for the C922". T-CAP-65: "the log holds it". T-CAP-67: "the recorder gets the encoded JPEG". T-CAP-74: "both are in the capture info (step 5d)". T-CAP-85: replaced by T-REC-42. |

The decisions D9, D38, D41, U4, U5 and U12 keep their text in section 20 of `windows-capture.md`.
VPF8 records that R1 to R4 and R5 replace their effect.

## 15. Measurements owed, open points, weak points, contradictions

### 15.1 Measurements owed

| ID | Measurement | When |
|---|---|---|
| T-REC-STALL, T-REC-KILL, T-REC-FSYNC, T-REC-GIL | Section 11 [R11] | Step 5a |
| T-REC-MF-DEFER | How Media Foundation behaves while the loop holds a frame for 0.5, 2 and 5 s [P §7]. With D26 the source keeps reading, so frames are replaced, not held back. A camera is needed. | After the connection |
| DT5 | The live byte offsets (T-REC-10) on each OS [SFF-757] | Step 5a |
| Blender | The frame count of a 5a MKV with missing rows in Blender 5.2.3 (SFT-711 external) | By the user, one time |

### 15.2 Open points

1. The UI display of the queue event [P §6: "shown in the UI"]. The status member of section 10 item
   11 exists. Who adds it to the UI, and in which phase, is open.
2. `capture_format` of the capture info has no value for NV12 (3b) [SFF-800 lists `MJPG` and `YUYV`].
3. The CI trigger for `dom/recorder` and for PRs to `development-streaming` (question Q3; open work
   of the decision log).
4. The fsync of the folder after a rename on Linux and macOS. SFF-786 does not ask for it; a rename
   can be lost on a power loss without it.
5. The camera-side drop that only the flag `DISCONTINUITY` shows [D34] is not in the CSV (7.1). The
   fit of step 5b counts frames by `source_frame_number` [SFF-777]. A frame that the camera dropped
   then shifts the fit by one period. Step 5b decides.
6. The proposals P-1 to P-6 wait for the user [R6].

### 15.3 Weak points

- The offset method of 6.3 rests on one behaviour of the FFmpeg Matroska muxer (it gives block k
  to the file at block k+1). It is [NV] until T-REC-10.
- The file-object writer (agent 6) differs from the path-based writer of each kill test of the
  research. T-REC-KILL must confirm the loss of one frame per kill.
- With the OpenCV source, a full queue drops frames in the driver, and `source_frame_number` shows
  no gap [cap 4.2]. Only `arrival_ns` shows the pause. This lasts until native capture on Linux and
  macOS (phase 7).
- A camera that dies while `give` waits is seen only after `give` returns, because the loop thread
  is blocked [cap 9.5].
- While `give` waits, the camera writes no ring slot. The preview of the group stops for that time.
- The 3 s queue and the 10 s stall limit are starting values until section 11 [R11].
- The research numbers come from one machine with one NVMe drive [M `RU/results/EVIDENCE_INDEX.md`
  §1].

### 15.4 Contradictions found

1. **R2 against SFF-754, SFF-759 and SFF-740.** The format counts rows as blocks and has no rule for
   a dead camera. P-1 and P-3.
2. **R3 against SFF-756 and SFF-758.** R3 calls the row a "gap row" and its count "the count of
   gaps". In the format, `gap` is a jump of `source_frame_number`, and `gaps=` counts that. P-1 adds
   the flag `missing` and the count `missing=`.
3. **R4 against SFF-793.** No program changes a file of the take before the user agrees. R4 has the
   main process complete the files. P-3.
4. **R8 against SFF-720, SFF-752, SFF-753 and SFF-803.** A label of today's 4-character `camera_id`
   fails SFF-753, the key is not a form of SFF-752, and no `key_origin` value means "provisional".
   Section 6.2 [agent 10] and P-5.
5. **R1 against SFF-775.** The fit lines are a MUST at a normal end; R1 puts the fit in 5b. A 5a
   take is not conformant on that point (6.4).
6. **R5 with R1.** No WAV from 5a and no Opus until 5b: the app records no audio between them
   (question Q1).
7. **[P §6] against D38 and R2.** "One camera fails mid-take: the whole take stops" [P §6]; D38 and
   R2 keep the other cameras. R2 replaces the plan sentence.
8. **D38 against R2.** D38 says "frame counts are then unequal across cameras". R2 makes the row
   counts equal again.
9. **[ring 5.2] step 6 and [ring 5.7] against SFF-734.** The ring inserts a DHT and gives the same
   object to the recorder queue; the format stores the camera bytes unchanged. Section 10 item 2
   [agent 21].
10. **SFF-736 with P-1.** "The frame at position k" is ambiguous when rows and blocks differ. P-2.
11. **SFF-757 (live offsets) against the evidence.** The muxer holds the last block
    [M `RU/results/write_throughput/FINDINGS.md` §2.3]. Thus a row can be written only one frame
    late (6.3) [agent 7].
12. **SFF-788 against the evidence.** A path-based PyAV MKV cannot be forced to disk
    [`RU/results/crash_resilience/FINDINGS.md` §4 item 10]. Agent 6 uses a file object; the kill
    evidence used a path.
13. **[P §6] "frame requests are held back" against D26.** With a push source, the source keeps
    reading and the waiting place replaces frames [cap 4.3, 6.5].
14. **[P §7] T-REC-GIL (cameras at 30 and 60 fps together) against D18.** D18 refuses that mix in one
    group. On synthetic frames with no gate, the mix is allowed (section 11).
15. **[cap 11.6] against SFF-800.** The capture info allows no other member. `input_range` has no
    place in the format (6.6) [agent 22].
16. **SFF-727 against R2.** The list of skellycam codes is closed, and R2 needs the manifest to name
    the dead camera. P-4.
17. **SFF-789 on Linux and macOS.** "The file lock of the operating system" is two different locks
    there. P-6.
18. **[ring 5.1] `frame_number` against [cap 5.3].** Already in [cap 17.2] item 2. The recorder does
    not write `frame_number`, so it does not matter here.

## 16. Choices of the agent

Each item fills a gap that R1 to R12, the format, the plan and the two accepted specs do not fix.
The body marks each one [agent n].

1. The package `skellycam/core/take_recorder/` and its file names; the tests in
   `skellycam/tests/take_recorder/`.
2. Two levels: the take level in the main process, the camera level in each camera process.
3. `give` waits while the queue is full, with the frame held by the loop thread; the stall limit
   counts the wait of one `give` call.
4. The queue size ⌈`QUEUE_SECONDS` × rate⌉ frames.
5. The writer thread is a non-daemon thread named `take-writer-<camera_id>`; the end marker is
   `None`.
6. The MKV through a Python file object (`open(path, "xb", buffering=0)`), not a path.
7. Row k is written after block k is in the file; `byte_offset` from `tell()`; the last block found
   by a read after the close.
8. The CSV unbuffered, one `write` per line.
9. The fsync of both live files once per second, on the writer thread, after a row.
10. `camera_key` = `camera_id` + 12 hexadecimal characters of the SHA-256 of `camera_id`; the label is
    its first 6 characters.
11. The take level writes each footer and each missing row after the end; the frame count of the
    take is the largest count of kept rows.
12. The completion of 7.4: cut both files to equal rows and blocks, missing rows, `# repair`, `# end`.
13. The last real frame is the position of the last row with a block.
14. The definitions of the stop response fields (8.2); `total_duration_sec` is the summary
    `duration_s`.
15. The lock calls (`msvcrt.locking`, `fcntl.flock`), retries every 50 ms up to 10 s, and what a
    timeout does at the start and at the end.
16. The take folder must not exist or must be empty; HTTP 422 for a bad `<rec>`, 409 for a folder
    with files or a lock timeout.
17. `purpose` is always `motion_capture` in 5a.
18. `clock_hz` is empty.
19. `group_position` is the order of the cameras in the take (the order of `camera_index`).
20. The nominal rate: `fps_num/fps_den` from Media Foundation; for OpenCV, a float rate within 0.01
    of 30000/1001 or 60000/1001 gives that fraction, and each other rate gives its value in
    thousandths, reduced.
21. The recorder gets the camera bytes before the DHT insertion.
22. The capture info values of 6.6, `device.backend` names, and `input_range` in the log only.
23. The playback list leaves out folders of the new format until phase 6.
24. A stall or a write error ends the take for every camera; the app keeps running.
25. The main process waits for each camera at most the stall limit after the last frame, then ends
    its process and completes its files.
26. The track size is the size of the opened mode; `stored_px` comes from the SOF of the first JPEG.
27. The test markers `recorder_slow` and `recorder_bench`, `SKELLYCAM_BENCH`, `SKELLYCAM_BENCH_OUT`,
    the synthetic JPEG sizes and the short CI form of the benchmark pass parts.
28. The conformance adapter `sff_adapter.py` with `TakeWriter` only, the commit pin and the file of
    expected results.
29. `exposure_us` = 2^v × 10^6 from the log2 exposure value.
30. The ring flags `DISCONTINUITY` and `DHT_INSERTED` do not go into the CSV in 5a.
31. The status member `recorder` and its five fields.
32. The fields of `CameraTakeResult`; a camera process whose writer did not finish ends itself hard.
33. A frame whose rotation differs from the take spec raises `ValueError`.

## 17. Questions for the user

Each question is worded so that "yes" accepts the recommended answer.

- **Q1. A microphone between 5a and 5b.** R5 stops the WAV and R1 brings Opus in 5b, so the app
  records no audio between the two steps. Option A: refuse a record start with a microphone, with
  HTTP 422 and the text "audio recording returns in step 5b; start again with no microphone".
  Option B: record the video only, and put a warning item in the start response. Recommended: A,
  because the user then never gets a take without the audio that the user asked for. **Question:
  between 5a and 5b, is a record start with a microphone refused with HTTP 422 (option A)?**
- **Q2. Container times after a missing row (P-2).** Option A: the container time counts the blocks
  (b / rate); OpenCV and Blender then count the frames exactly, as the evidence shows for index
  times; after a missing row, Blender frame n of that camera is multi-camera frame n + 1. Option B:
  the container time counts the rows (k / rate), so a missing row leaves a one-frame hole; a player
  that places frames by time keeps the cameras in step, but what OpenCV and Blender count with a
  hole is [NV]. Recommended: A, because only A has evidence, and the CSV keeps the true position of
  each frame. **Question: does the container time count the blocks (option A)?**
- **Q3. CI on the three systems.** Option A: one CI change that runs `test.yml` (Windows, Linux and
  macOS) on each push to `dom/recorder`, as
  [ADR-7DE6](../decisions/entries/7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md) does for
  the arm64 job on `dom/native-jpeg`.
  Option B: no CI change; the tests run on the machines of the user only. Recommended: A, because
  the user requires parity and CI has runners for the three systems; a push still needs the word of
  the user. **Question: does a CI change run the tests of 5a on the three systems on each push to
  `dom/recorder` (option A)?**

## 18. Decisions of the user

The user decided these on 2026-11-19, in the grilling of Q205 to Q216
([ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)). They are binding.

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

Decided before this grilling (cited, not repeated): the format (skellyfileformat SPEC, draft v2: one
MKV per camera with `V_MJPEG`, camera bytes unchanged; one CSV per camera with a CRC and a flush for
each row; the manifest; the capture info; the folder layout); the writer design (one writer thread
per camera process, a bounded queue of about 3 s; a full queue slows capture and never drops a
frame; a stall over the limit ends the take with an error; a write error finishes the sidecars and
the manifest for the frames written); PyAV 19.0.2 for the MKV; recorder first, ring write after
([ring 5.3]); read old formats, never write them; Opus in fragmented MP4 for audio (step 5b).
