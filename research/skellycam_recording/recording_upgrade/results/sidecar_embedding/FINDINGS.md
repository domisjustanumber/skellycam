# Sidecar embedding and external playback of JPEG-in-MKV

2026-11-12, Gerald (Windows 11, i7-14700K). Written for the capture + recording plan (`research/CAPTURE_AND_RECORDING_PLAN.md`, rev 3.5). Scripts are in `scripts/sidecar_embedding/`. The test MKVs are rebuildable and were not kept.

**Labels:** **[M]** measured (result file or command), **[S]** spec, **[C]** code read, **[I]** inferred, **[NV]** not verified.

**Versions:** PyAV 19.0.2 with libavformat 63.1.102 (FFmpeg 9.0.2), from the `skellycam-phase1` worktree's venv; the main checkout's `.venv` still has PyAV 18.0.0 [M]. FFmpeg CLI 9.0.2, VLC 3.0.24, OpenCV 5.0.0 (`opencv-contrib-python==5.0.0.93`), Node 24.15.0, Electron 35.7.5 (Chrome 134) and 45.2.3 (Chrome 156).

## 0. Answers

| Question | Answer |
|---|---|
| Does VLC play JPEG-in-MKV? | **Yes** [M]: MKV demux plus the avcodec MJPEG decoder; every frame decoded, apart from at most one at end of file, which is a quirk of the frame-dump method (§1). It plays at the nominal rate, because container timestamps are frame indexes. |
| Can the sidecar go inside the MKV and stay compatible with players? | **Yes,** as a Matroska attachment. VLC, ffprobe and OpenCV are unaffected [M] (§2, §5). |
| Is there always room to embed it? | **Yes,** for any finalised file FFmpeg writes to seekable output without attachments of its own. FFmpeg's SeekHead reserve has an Attachments slot by design [C], and it held in every case tested, including files over 4 GiB with every slot used [M] (§3). |
| Can the browser player find an embedded sidecar? | **Yes:** 3 Range reads from the start of the file, with no file size needed. Works under `file://` in Electron 35 and 45 [M] (§4). |
| Is it a blocker? | **No.** The separate sidecar stays primary for recording and crash recovery; embedding is a finalise step (§7). |
| Does audio matter? | **Yes, for offsets.** Any remux to add audio moves every frame and changes the Segment UID. Muxing FLAC audio in the same pass breaks live offsets. Offsets must be rebuilt against the final bytes, in skellycam and in skellysync Design A (§6.5–6.7). |

## 1. External playback (VLC)

Method: run VLC headless (`-I dummy --vout=dummy --video-filter=scene --scene-ratio=1`), which writes every decoded frame as a PNG, then count the PNGs.

| File | Frames in file | PNGs | Notes |
|---|---|---|---|
| FFmpeg CLI, testsrc2 720p MJPEG | 90 | 89 | `using video decoder module "avcodec"`, `codec (mjpeg) started` |
| Same file with a 4,800 B attachment added by `ffmpeg -attach` | 90 | 89 | attachment listed in VLC's log |
| PyAV 19 file, recording-style (index PTS, `flush_packets=1`) | 90 | 90 | |
| PyAV 19 file with the sidecar appended at the end (§2) | 90 | 89–90 | 89 on one appended file, 90 on another |
| PyAV 19 crashed file, remuxed, then appended | 60 | 60 | |
| PyAV 19, 4.68 GB, seek to 2270 s of 2280 s, then decode to the end | 300 left | 299 | no `mkv error`; attachment found |

- [I] The single missing frame at end of file is the frame-dump method stopping, not a decode failure: the same file type gives 89 or 90 between runs.
- Synthetic frames only. Real C922 and C930e JPEGs (`DQT SOF0 DHT… COM APP0 DRI SOS`) go through the same FFmpeg MJPEG decoder that OpenCV uses on them [I].
- Other FFmpeg-based players (mpv, ffplay, MPC-HC) [NV]. QuickTime and Safari don't open MKV [I]. Browsers reject MJPEG in any container [M] (`chromium_codecs/FINDINGS.md` C1, C2).
- With index PTS, an external player shows nominal-rate playback, not true time: a recording with drops plays shorter than the event.

**Pitfall found here (applies to the real writer).** PyAV switches the MKV stream's time base from 1/30 to 1/1000 when it writes the header. A writer that sets `packet.time_base = stream.time_base` for every packet stamps frames 1 ms apart after frame 0 (pts 0, 1, 2, …). VLC then drops about 87 % of them as "too late" (12/90 PNGs) [M]. The fix is to give packets a fixed `Fraction(1, fps)`, or to read the time base after `start_encoding()`, as `python_integration/recwriter.py` does [C]. With the fix: pts 0, 33, 67, 100 and 90/90 PNGs [M]. An earlier generator script (`attach_locate/make_pyav.py`, not kept) had this bug.

## 2. Embedding: where the attachment goes

- **`ffmpeg -c copy -attach` puts Attachments before the first Cluster.** The first JPEG moved from byte 550 to 5,468, so every sidecar offset was wrong [M]. Any later `ffmpeg -map 0 -c copy` remux does the same and also changes the Segment UID (cc82… → fcc5…) [M].
- **RFC 9559:** Attachments "MAY be placed before the first Cluster"; when the file is likely to be edited, "it SHOULD be placed after the last Cluster" (§6.7). "SeekHead element(s) MUST be updated" when Top-Level Elements are added; Void padding may be consumed (§6.1). A second SeekHead "MUST only reference Cluster elements" (§6.3), so a second SeekHead can't point at the attachment [S].
- **Our appender** (`append_attachment.py`, about 120 lines, standard library only):
  1. append `Attachments{AttachedFile{FileName, FileMediaType, FileUID, FileData}}` at EOF;
  2. rewrite the 8-byte Segment size in place;
  3. rewrite the SeekHead with one more entry (CRC-32 kept) inside the old SeekHead + Void span, padding the rest with Void.

  It refuses an unknown-size Segment (crashed file), a Segment that doesn't end at EOF, a file that already has Attachments, and a SeekHead with no room. It never moves frame data.
- Changes to the original bytes: 25–26 bytes, all inside the first 155 bytes [M].

## 3. Is there always room in the SeekHead?

**By design [C]** (`libavformat/matroskaenc.c` n9.0.2; identical constants in n8.0 and n8.1.2):
- `MAX_SEEKHEAD_ENTRIES 7` (line 77): "Info, Tracks, Chapters, Attachments, Tags (potentially twice) and Cues". `MAX_SEEKENTRY_SIZE 21` (line 271).
- The reserve is `7 × 21 + 14` = 161 bytes (line 907), written as Void at the header and filled in at the trailer. It's only written when the output is seekable and not `live` (`IS_SEEKABLE`, line 90).
- A Seek entry is 13 bytes + the SeekPosition width: 14 bytes for a position under 256 B, 18 past 4 GiB, and 21 only at the 2^56 maximum.
- Without attachments FFmpeg uses at most 6 entries: 6 × 21 + 6 (CRC-32) + 6 (SeekHead ID and size) = 138 bytes, which leaves 23 = one 21-byte entry + the 2-byte minimum Void.

**When FFmpeg writes Tags twice [C].**
- The first Tags element is written in the header: the global metadata and each track's reserved DURATION tag (`mkv_write_tags`, around line 2347).
- If chapters are first set after the header, they're written at the trailer (line 3315). Their metadata then goes into a *new* Tags element, because "if mkv_write_tags() has already been called, then any tags corresponding to chapters will be put into a new Tags element" (lines 2428–2430). That element gets its own SeekHead entry (line 2482).
- Triggered with PyAV by calling `set_chapters()` after muxing, with chapter metadata `COMMENT`. Result: Info, Tracks, Tags, Chapters, Tags, Cues [M].
- skellycam doesn't plan chapters, so real recordings have 4 entries.

**Measured (PyAV 19.0.2)** (`matrix.json`, `big.json`). Sidecar payload: 64 B header + 64 B per frame.

| File | Entries before | Bytes used of 161 → after append | Spare after | Frames unchanged | ffprobe count | Attachment identical |
|---|---|---|---|---|---|---|
| 90 fr, no tags | 4 | 70 → 86 | 75 | 90/90 | 90 | yes |
| 90 fr, tags | 4 | 70 → 86 | 75 | 90/90 | 90 | yes |
| 90 fr, tags + chapters at header | 5 | 85 → 101 | 60 | 90/90 | 90 | yes |
| 54,000 fr (540 MB), tags | 4 | 71 → 88 | 73 | 54,000/54,000 | 54,000 | yes |
| 54,000 fr, tags + chapters | 5 | 86 → 103 | 58 | 54,000/54,000 | 54,000 | yes |
| Killed at frame 61 | no SeekHead; **append refused** | — | — | — | — | — |
| … after a PyAV stream-copy remux | 4 | 70 → 86 | 75 | 60/60 | 60 | yes |
| 90 fr, chapters set after the header | **6** | 102 (before) | 59 (before) | — | — | — |
| **68,400 fr, 4.68 GB, tags** | 4 (Cues at 4.68 GB, 5-byte position) | 72 → 90 | 71 | 68,400/68,400 | 68,400 | yes |
| **68,400 fr, 4.68 GB, tags + chapters set after the header** | **6** (Chapters, Tags, Cues past 4 GiB) | 108 → 126 (7 entries) | **35** | 68,400/68,400 | 68,400 | yes |

- "Frames unchanged" = same (pos, size, pts) from ffprobe, and the JPEG bytes identical. On the 4.68 GB files: the SHA-256 of every byte after the SeekHead + Void span is the same before and after; 5,614 frames sit past 4 GiB.
- Append time: 20 ms for a 5.2 MB payload on 6 MB (sub-agent run); 557–657 ms for 4.4 MB on 4.68 GB, mostly the fsyncs [I].
- Not covered by the guarantee: unseekable output, `live=1`, crashed files before their remux, files that already carry an attachment. The appender refuses all of these rather than corrupting the file [C].

## 4. Finding the embedded sidecar from the browser

`locator.js` (99 lines). Reads: 4 KB at offset 0 (EBML header, SeekHead, Info with the Segment UID) → 512 B at the Attachments position → the FileData. It never walks Clusters, so lacing and unknown-size Clusters don't matter. Arithmetic uses `v * 256 + b` (exact to 2^53), not 32-bit shifts.

| Case | Result | Reads |
|---|---|---|
| Appended file, Node and Electron `file://` (E35, E45) | ok, SHA-256 identical, 2.2–5.5 ms | 3 |
| Appended 4.68 GB files (Node), FileData at 4,680,533,554 | ok, identical, 1.7 ms | 3 |
| Plain file | `no-attachments-entry` | 1 |
| Crashed file (unknown-size Segment, no SeekHead) | `no-seekhead` | 1 |
| SeekHead pointing at the wrong element | `stale-seekhead` | 2 |

Under `file://` in E35.7.5 and E45.2.3: Range requests return the right bytes with status 200, but no response carries `Content-Range` or `Content-Length`, HEAD included. So the page can't learn the file size; explicit and suffix ranges both work [M] (`electron_result_e35.json`, `electron_result_e45.json`). Through skellycam's own HTTP route [NV].

Options compared by the sub-agent:
- (b) the server parses the file and serves the sidecar: one read, but needs the server.
- (c) a footer found by a suffix read: breaks if anything is appended after it.
- (d) a second SeekHead: not spec-valid.

Option (a), the head-anchored reader above, is recommended.

## 5. OpenCV (freemocap's reader) on appended files

`spec_checks.json` S3, OpenCV 5.0.0 `CAP_FFMPEG`:

| File | `CAP_PROP_FRAME_COUNT` | Frames read | `POS_FRAMES` seeks (pixel hash) | Decoded frames vs the original |
|---|---|---|---|---|
| 90 fr, appended | 90 | 90 | 11/11 | identical |
| 18,000 fr, appended | 18,000 | 18,000 | 11/11 | identical |

The originals gave the same numbers.

## 6. Facts the sidecar spec depends on

1. **Offsets can be recorded live, one frame late** (`spec_checks.json` S1). With `flush_packets=1`, FFmpeg's MKV muxer holds back one packet: after `mux(i)` the file ends exactly at the end of frame i−1's JPEG. This held for 89/89 frames (720p) and 2,699/2,699 (240p, across many Clusters). So `offset[i−1] = st_size after mux(i) − len(jpeg[i−1])` [M]. The last frame's offset is known only after `close()`. With `flush_packets=0` this fails (0/89): data sits in a 32 KB I/O buffer.
   - This is also why the crash tests lost exactly 1 frame per kill with MKV + fp [I, consistent with `jpeg_passthrough/FINDINGS.md` GF02].
   - The cost of one `os.stat` per frame at 16 × 1080p60 [NV].
2. **The Segment UID is on disk right after `start_encoding()`** with `flush_packets=1`, and unchanged at close (2/2 files) [M]. The writer can put it in the sidecar header at start. With `flush_packets=0` the file is still 0 bytes after the header.
3. **Any remux makes new offsets and a new Segment UID** [M] (§2). This affects:
   - crash recovery (row 1.7);
   - the audio remux: `skellycam/core/recorders/video_audio_remuxer.py:28-39` writes `<video>.remux.mp4` and moves it over the original. It's disabled today (`recording_finalizer.py:63`, commented out) [C].

   The sidecar's offsets and UID have to be regenerated after any remux.
4. **The existing code already embeds metadata in the container:** the remuxer writes `output.metadata["skellycam_data"] = json.dumps(...)` as a global tag (`video_audio_remuxer.py:64`) [C]. Matroska tags fit global fields; the per-frame table needs an attachment.
5. **Audio breaks live offsets, depending on the codec** (`audio_offsets.json` S4; 1,800 frames, 48 kHz mono audio muxed in step with the video, 1,600 samples per frame):

   | Audio in the same mux pass | After `mux(video i)`, the file ends at frame i−1 |
   |---|---|
   | none | 1,799/1,799 |
   | PCM s16le | 1,799/1,799 |
   | FLAC | **0/1,799** (the encoder releases packets in bursts, so the held-back packet is audio) |

   So with audio in the file, live offsets are codec-dependent and can't be relied on [M].
6. **Rebuilding offsets from a finished file is cheap and exact** (`audio_offsets.json` S5; 18,000 frames of 240p, warm disk cache):

   | Method | No audio (180 MB) | FLAC audio (188 MB) | Matches the JPEG bytes |
   |---|---|---|---|
   | EBML walk reading only element headers (`audio_offsets.py`, about 50 lines, no FFmpeg) | 112 ms | 116 ms | 18,000/18,000 |
   | PyAV demux, `packet.pos + 4` | 63 ms | 86 ms | 18,000/18,000 |

   Cold-cache and HDD times, and 1080p files [NV]. The `+ 4` assumes a 1-byte track number and no lacing, which FFmpeg uses for video [C/M]; the EBML walk reads the real header length instead.
7. **Adding audio by remux afterwards moves every frame** (`audio_offsets.json` S6): 0/1,800 offsets unchanged (sizes all unchanged), and a new Segment UID [M]. This is the shape of:
   - skellysync's ReattachAudio today: `ffmpeg -i video -i wav -c:v copy -c:a aac` into a temp file, then moved over the output (`skellysync_jpeg/SCOPE.md` §1.1; `core/backends/ffmpeg.py:264-290`) [C];
   - skellycam's disabled audio remuxer.

   **So any producer that re-encodes or remuxes, skellysync Design A included, must write the sidecar's offsets and UID against the final bytes, after the audio step, never before.**

## 7. Recommended design

1. **While recording:** a separate binary sidecar, appended and flushed per frame. When the MKV holds video only, record i−1 is written after `mux(i)`, with its offset; the last record is written after `close()`. Every record then describes a frame that is complete on disk [I; to be checked by T-KILL]. Live offsets are a convenience for crashed or in-progress files only, never the final values.
2. **Header** carries the Segment UID, read after `start_encoding()`.
3. **Finalisation order, for every producer (the skellycam writer, crash recovery, exports, skellysync Design A):**
   1. any remux or audio mux;
   2. rebuild every offset by scanning the final MKV (about 0.1 s per 18,000 frames, warm cache) and check each frame's CRC;
   3. write the final UID;
   4. timestamp CSVs;
   5. optionally embed with the appender.

   The scanner, the appender and the record codec belong in the shared sidecar module (skellysync D-PKG).
4. **Player:**
   - Use the separate sidecar when it exists (1 read); otherwise run the locator (3 reads).
   - Reject a sidecar whose Segment UID doesn't match the file's; the locator reads the UID from the first 4 KB.
   - If both are missing or rejected, rebuild the index by scanning [I].
5. **CI tests against the pinned PyAV:**
   - SeekHead + Void span − used ≥ 23 bytes;
   - after `mux(i)` the file ends at frame i−1;
   - the first packets' pts are 0, 33, 67 ms.

## 8. What is still open before the sidecar spec can be locked

### 8.1 A proposed layout to react to [I]

Little-endian, fixed-size records, with the header's `record_size` letting a later version append fields.

**Header** (fixed part; a length-prefixed UTF-8 JSON block after it for the descriptive fields):
- magic `SKFR`, `version`, `header_size`, `record_size`, flags;
- Segment UID (16 B; zero until known);
- stable camera key;
- format fourcc, width, height, nominal rate as a rational;
- encoder and quality setting;
- host clock id (QPC / `CLOCK_MONOTONIC` / `mach_absolute_time`) and its frequency;
- a (host ns, UTC ns) anchor pair taken at start, replacing today's one pair per group (`timebase_mapping.py:22-24`).

The JSON block carries the controls, the producer (skellycam / skellysync) and its version, and skellysync's source and sync fields (`skellysync_jpeg/SCOPE.md` §2.8).

**Record, 64 B:**

| Bytes | Field | Notes |
|---|---|---|
| 0–7 | `arrival_ns` i64 | host monotonic (QPC on Windows) |
| 8–15 | `sample_time_ns` i64 | MF sample time × 100, same timebase [M] (`timestamp_accuracy_options.md:398`); INT64_MIN when absent |
| 16–23 | `legacy_ns` i64 | today's stamp, so the existing CSV columns keep their meaning (row 1.6) |
| 24–31 | `fitted_ns` i64 | INT64_MIN until finalisation writes the lattice fit |
| 32–39 | `offset` u64 | JPEG start in the MKV; live value provisional, rebuilt at finalisation |
| 40–43 | `size` u32 | |
| 44–47 | `jpeg_crc32` u32 | zlib CRC-32 of the JPEG bytes |
| 48–51 | `source_frame_number` u32 | camera/capture sequence; gaps = drops |
| 52–55 | `write_index` u32 | 0..N−1 = the recording frame number freemocap pairs by |
| 56–59 | `flags` u32 | gap, repeat, PTS bumped, fit valid, fit unreliable, offset final |
| 60–63 | `record_crc32` u32 | over bytes 0–59 |

Finalisation already rewrites every offset, so it can fill `fitted_ns` and the flags in place too. Then the sidecar is the single per-frame table, and the CSVs are derived from it. Size: 6.9 MB per camera-hour at 30 fps.

### 8.2 Decisions (for Dom)

| # | Question | Options | Recommendation |
|---|---|---|---|
| S1 | Record content and size | the 64 B layout above · the prototype's 48 B (no offset, one time) · a different set of times | 64 B as above |
| S2 | Which time the player uses, and where the fitted time lives | the fitted time in the sidecar, written at finalisation · arrival only · the fitted time only in the CSV (as row 1.6 says now) | the fitted time in the sidecar; the player uses it when "fit valid", else arrival |
| S3 | **Audio placement** (skellycam, and skellysync D-AUDIO) | separate WAV per camera · audio track in the MKV, muxed in the same pass · track added by remux | **separate WAV**: the MKV stays video-only, live offsets stay valid (§6.5), and nothing is remuxed. A track in the MKV is workable only if offsets are rebuilt after the audio step (§6.6–6.7) |
| S4 | Embed by default? Keep the separate file after embedding? | embed + keep · embed + delete · export/archive only | embed at finalisation and keep the separate file; the Segment UID check covers divergence |
| S5 | Where the format code lives (skellysync D-PKG) | small shared package · vendored module with a shared test vector · skellysync imports skellycam | small shared package: record codec, offset scanner, appender, plus the JS reader and a golden test file |
| S6 | Names | sidecar `<stem>.skfr`? attachment name `skellycam_frames.skfr`, MIME `application/x-skellycam-frames`? | settle once, in the shared package |
| S7 | Overlays (`.skov`) | separate file · a second attachment by the same mechanism | second attachment at finalisation, the same rules |
| S8 | Recording-level manifest | extend the recording info JSON · a new manifest | extend the info JSON: per camera the MKV, the sidecar, the key, the Segment UID |

### 8.3 Tests still needed

| # | Test | Why | Where |
|---|---|---|---|
| T-S1 | With records written one frame behind: after every kill, records = complete frames on disk (0 mismatches), and a torn last record is caught by its CRC | the crash claim in §7 item 1 is [I] | TP2 T-KILL |
| T-S2 | Cost of one `os.stat` per frame at 16 × 1080p60 (write latency p99.9 with and without) | live offsets must be nearly free, or drop them and rely on the finalisation scan | TP3 |
| T-S3 | Offset rebuild on a cold cache, 1080p, 1 h, SSD and HDD | finalisation and crash-recovery time | TP2 |
| T-S4 | Player sidecar load: 16 cameras × 1 h ≈ 110 MB at 64 B; fetch, parse and memory in Electron, against a compact time + offset + size index | may decide lazy loading or a columnar section | TP4 |
| T-S5 | Range reads (explicit and suffix) through skellycam's FastAPI route and Electron `protocol.handle` | the locator was tested under `file://` only | TP4 |
| T-S6 | `mjpeg_qsv`'s 3-call delay: every record pairs with its own source frame and times (CRC + pts) | encoder output order ≠ capture call order | TP2 M3 |
| T-S7 | Linux/macOS clock ids and anchors | the header names the clock | phase 1b suites |
| T-S8 | CI guards on the pinned PyAV: SeekHead room ≥ 23 B; pts spacing of the first packets; one-behind file end (only if live offsets are kept) | catch FFmpeg/PyAV changes at bump time | release checks |
| T-S9 | The UID check in the player: a file remuxed by ffmpeg is rejected, then re-indexed by scan | §2's silent-offset risk | TP4 |
| T-S10 | A shared golden file (MKV + sidecar, separate and embedded) read by the Python and JS readers | two producers (skellycam, skellysync) and two readers must agree | shared package CI |

## 9. Files
- `scripts/sidecar_embedding/`:
  - `append_attachment.py`, `locator.js`, `node_test.cjs`, `ebml_dump.py`, `verify.py` (sub-agent, 2026-11-12);
  - `matrix.py`, `big.py`, `spec_checks.py`, `audio_offsets.py`;
  - `electron_test/` (`main.cjs`, `page.html`).
- `results/sidecar_embedding/`: `matrix.json`, `big.json`, `spec_checks.json`, `audio_offsets.json`, `electron_result_e35.json`, `electron_result_e45.json`.
- Run `matrix.py`, `big.py`, `spec_checks.py` and `audio_offsets.py` with the `skellycam-phase1` venv (`python -I <script> <outdir> <720p source mkv> …`). The 720p source was `ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 -frames:v 90 -c:v mjpeg -q:v 3 -pix_fmt yuvj422p`; the 240p source used 320x240, 900 frames, `-q:v 5`, `yuvj420p`.
