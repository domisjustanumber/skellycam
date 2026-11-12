# Digest for drafting skellyfileformat `spec/SPEC.md` v0 and `spec/conformance.md`

2026-11-12. Inputs for drafting skellyfileformat `spec/SPEC.md` v0 and `spec/conformance.md` (plan step 5).

*Written by a sub-agent (read-only; no network, cameras or heavy commands); saved by the main session. Before saving, the main session checked the 64 B record layout against `scripts/encoder_pairing/eplib.py:34-41` (`<qqqqQIIIII` + CRC; field order as in §5) and the `.skau` prototype header and packet table against `scripts/flac_skau/flac_skau.py:155-157`. Every layout here is a prototype unless an ADR says otherwise. The final list, "Decisions Dom must still make", is the agenda before the draft.*

This was a read-only task. I edited, created and committed nothing, and I ran no network, camera or heavy commands.

## Abbreviations and labels

**Labels.** [C] = read in code or a doc. [M] = measured, with the result file named. [I] = inferred. [NV] = not verified.

**Roots.**
- SFF = the skellyfileformat checkout.
- SC = the skellycam checkout, branch `dom/research`.

**Documents.**
- **P** = SC `research/CAPTURE_AND_RECORDING_PLAN.md`, rev 3.10. Line numbers:
  - §2.2: 75–85
  - §2.7: 142–175 (S1 167, S2 168, S4 170, S5 171, S6 172, S8 174, S9 175)
  - §2.8: 177–216
  - §2.9: 218–248
  - plan rows: 1.4 at 271, 1.5 at 272, 1.6 at 273, 1.7 at 274, 1.9 at 276, 1.13 at 280
  - TP2 T-KILL: 326–330
  - TP4 sidecar tests: 359–362
  - release checks: 370–379 (T-MKV at 374–379)
  - decisions D14–D26: 436–448 (D15 437, D16 438, D17 439, D18 440, D19 441, D21 443, D22 444, D23 445, D25 447, D26 448)
- **R** = SC `research/skellycam_recording/recording_upgrade/results/`
- **S** = SC `research/skellycam_recording/recording_upgrade/scripts/`

**FINDINGS files** (all under R):

| Short name | File |
|---|---|
| SE | `sidecar_embedding/FINDINGS.md` |
| SL | `sidecar_load/FINDINGS.md` |
| EP | `encoder_pairing/FINDINGS.md` |
| ST | `stat_cost/FINDINGS.md` |
| RT | `range_transport/FINDINGS.md` |
| AC | `audio_skellycam/FINDINGS.md` |
| AS | `audio_skellysync/FINDINGS.md` |
| FS | `flac_skau/FINDINGS.md` |
| RF | `rotation_flag/FINDINGS.md` |
| EI | `EVIDENCE_INDEX.md` |

**Other documents.**
- MFR = SC `research/skellycam_recording/docs/manifest_field_review.md`
- RFF = SC `research/skellycam_recording/docs/recording_folder_files.md`
- SCOPE = SC `research/skellysync_jpeg/SCOPE.md`
- TAO = SC `research/usb_cameras/docs/timestamp_accuracy_options.md`

All [M] results come from one Windows 11 machine. Linux and macOS have had no hardware run (P:5).

---

## 0. Cross-cutting facts and constraints for the whole spec

**Byte order and integrity**
- Little-endian everywhere. Every prototype struct uses `<` [C].
- CRC is zlib CRC-32 (the IEEE/ISO-HDLC CRC-32) in every prototype [C].
- The EBML CRC-32 element in the SeekHead is the same zlib CRC, stored little-endian (S `sidecar_embedding/append_attachment.py:91-93`, citing RFC 8794 §11.3.1) [C].

**Times and offsets**
- Every time is an integer in nanoseconds (i64). INT64_MIN means "absent" (SE §8.1 rows `sample_time_ns` and `fitted_ns`; AC §4.2 `pa_adc_ns`) [C].
- The JS reader reads each i64 as two u32 halves, not BigInt (ADR-69YS item 5).
  - BigInt is 3.9–4.2× slower [M] (SL §2, `summary.json`).
  - A time minus a recording base is exact within 2^53 ns (104 days). An offset is exact below 2^53 (SL §6.4) [M/I].

**Spec process constraints**
- Rule 3 of `tools/check_spec_traceability.py` (lines 18–25) requires IDs in number order within each file [C].
- AGENTS §4 says "give a new requirement the next free number".
- Together, these mean a requirement added later to an earlier section breaks the ordering rule. Dom should decide a numbering scheme now (see decision 1 at the end) [I].
- A provisional requirement has `(provisional)` after its ID and names its open item (SFF `spec/SPEC.md:18-19`) [C].
- There is no section yet for the whole recording, which ADR-5PP8 requires. SPEC.md headings run 1–14 plus Appendix A [C].

---

## 1. Scope and terms

### Decided rules

- **The format covers these files:** the camera MKV (one JPEG track, every frame a key frame); the video timing sidecar (an attachment, or a separate file until finalisation or after a crash); the skellycam `.audio.mka` with one FLAC track and its `.skau` as an attachment; and the skellysync FLAC track in each camera MKV. Source: SFF README "Scope (normative)" [C].
- **The format describes a whole recording (one take):** which files make it up; the folder layout and names; the one shared clock; how a writer records the set; how a reader opens it, also when it is crashed or incomplete; the recording manifest; and how to find a file that is not in this format. Source: ADR-5PP8 item 1 [C].
- **Out of scope:**
  - legacy formats (ADR-X7FT item 6; ADR-5PP8 item 5);
  - skellycam's recording info JSON (ADR-5PP8 item 4);
  - overlays: there is no `.skov` and no overlay attachment (ADR-5K7G items 2 and 4; recorded freemocap overlays may be added later, for example as CBOR in CRC-framed records);
  - Opus (ADR-CA03 item 1);
  - the player transport, which is a skellycam spec (P D20, D22);
  - lossless and Bayer formats (P §5).
- The spec must let another program implement the format from the spec alone (ADR-VJ14 item 4).

### Terms the draft needs

Recording/take, camera file, audio file, video timing sidecar (separate or embedded), `.skau`, packet table, live offset, final offset, finalisation, finalised / unfinalised / crashed / recovered, writer, reader, player, producer (skellycam recorder, skellycam converter, skellysync), Segment UID, host clock, arrival time, sample time, legacy time, fitted time, player time, `write_index`, `source_frame_number`, nominal rate, legacy recording, golden file.

### Measured facts

None specific to this section.

### Gaps

- **"Producer" kinds.** The converter (S10c) writes this format from old CSVs, and skellysync writes from source files with no host-clock capture (SCOPE §2.8). The meaning of the time fields differs per producer, so the terms must cover that (see §5 conflict 5) [I].
- **Frame label.** P row 1.8 (P:275) says the player labels each tile with `connection_frame_number` "from the sidecar". No field has that name. It is probably `source_frame_number`, while `write_index` is the recording frame number that freemocap pairs by (SE §8.1) [I]. The term mapping must be stated.

### Candidate tests

None beyond the per-section tests.

---

## 3. Versioning

### Decided rules

All from SFF README "Versioning (normative)" and "Compatibility promise", and ADR-M4DF:

- **Format version.** It is the `major.minor` of the skellycam release that last changed the format.
  - A change that an older reader cannot read needs a skellycam major version.
  - An added field needs a minor version or more.
  - A patch release does not change the format.
- **Header fields.** Each sidecar header (the video sidecar and the `.skau`) holds three u16 fields: `major`, `minor` and `prerelease`. `prerelease` is 0 for a released format and N for the Nth prerelease revision.
- **Reader.**
  - MUST refuse an unknown `major`.
  - MUST read a higher `minor` of a known `major`, and skip unknown fields.
  - A conforming reader MUST read every released version (`prerelease` = 0).
  - A file with `prerelease` > 0 has no promise. A later reader MAY refuse it.
- **Writer.** A writer writes only the latest version.
- **Writer string.** Each sidecar holds a writer string, for example `skellycam 2.1.0`. It is for diagnostics only. A reader MUST NOT change its behaviour because of it. skellysync writes the format version that skellyfileformat gives (M4DF item 5).
- **Package version.** The package `major.minor` = the format version. The patch number counts library fixes (M4DF item 6).
- Provisional parts must close before v2.0.0 (ADR-5PP8 item 11; open-work.md) [C].

### Byte layouts in prototypes (none matches ADR-M4DF; all are prototypes)

| Source | Layout | Version field |
|---|---|---|
| S `encoder_pairing/eplib.py:42` | `HDR_FMT = "<4sIIIIII16s20s"`: magic `SKFR`, `version` u32, `header_size` u32, `record_size` u32, `width`, `height`, `fps` (integer u32), `encoder` 16s, pad 20 = 64 B | one u32 |
| S `flac_skau/flac_skau.py:155` | `b"SKAU" + struct.pack("<HHII", 1, 64, 48, 0)` + 48 random bytes = 64 B | `version` u16 = 1 |
| S `audio_skellycam/pipeline.py:33` | `"<4sHHHH16sIIHHBxxxQqq"` + CRC32 | `version` u16 |
| SE §8.1 [I] | magic `SKFR`, `version`, `header_size`, `record_size`, flags | one field |

### Conflicts and gaps

1. Every prototype header carries a single `version`. ADR-M4DF requires the u16 triple. The draft must place `major`/`minor`/`prerelease` at fixed early offsets, so that a reader can decide to refuse before it parses anything else [I].
2. **Writer string encoding is undefined.** Length, encoding (UTF-8?) and position (fixed-width field or length-prefixed) are not decided.
3. **Rules for skipping unknown data are needed:**
   - `header_size` and `record_size` must be in the header, so that a higher minor can append fields (SE §8.1 says "the header's `record_size` letting a later version append fields").
   - ADR-69YS item 1 says "one fixed 64-byte record". Can a later minor grow the record? If yes, where does the record CRC sit (always the last 4 bytes, covering the bytes before it?) (see decision 8).
   - Readers must ignore unknown flag bits, and writers must set them to 0 (not decided).
4. **Which version do prerelease builds write now?** The README says no version is released, and v2.0.0 is the target. A prerelease skellycam would write `major`=2, `minor`=0, `prerelease`=N [I]. Dom must confirm.
5. **Manifest version.**
   - MFR §E (lines 134–136): if the manifest is in the spec, use `"skellyfileformat": {"major","minor","prerelease"}`; every listed header must share the major; headers win; any manifest edit is a format change [C].
   - Not decided.
6. **The `.mka` and the camera MKV carry no version** of their own. Their version is the version of their sidecar [I].

### Candidate tests

- Reader refuses unknown `major` (generated header with `major`+1). Pass: an error, no data returned.
- Reader reads a higher `minor` with extra header bytes and a larger `record_size` (generated). Pass: known fields equal the expected values.
- Reader with a prerelease file: the reader MAY refuse. A writer test checks that a released writer writes `prerelease`=0.
- Reader output does not depend on the writer string (two golden files that differ only in the writer string). Pass: identical results.
- Unknown flag bits are ignored (generated). Pass: identical player time and offsets.

---

## 4. Video: the MKV profile

### Decided rules

1. **JPEG only; every frame is a key frame.**
   - For an MJPEG camera, the stored JPEG is the camera's own bytes, unchanged (passthrough).
   - Raw streams are encoded to JPEG at target A.
   - Sources: P §2.1, row 1.5; ADR-X7FT item 2; README.
2. **Frames are stored in sensor orientation.**
   - No pixel rotation (ADR-CE4D item 1).
   - **No container rotation flag**, for example `Projection`/`ProjectionPoseRoll` (ADR-CE4D item 3).
3. **Container timestamps = frame index at the nominal rate.**
   - Packets get a fixed `1/fps` time base, never `stream.time_base` copied after the header (P row 1.5; SE §1).
   - Container pts = `write_index` (EP §5 rule 3).
4. **`flush_packets=1`** (P row 1.5).
5. **The skellycam camera MKV stays video-only.** Audio is a separate `.audio.mka` (P row 1.5; ADR-CA03).
6. **skellysync camera MKV:** exactly one MJPEG stream and one audio stream, in the same pass (AS §5.1 step 4; ADR-CA03 item 3).
7. **Do not use `ffmpeg -attach`** (ADR-77Z3 "Not repeated").
8. **No overlays and no burned-in stamp** in recorded frames (ADR-5K7G item 1). This is a skellycam behaviour, and hard to test as a format rule.

### Measured facts

- **Index timestamps keep OpenCV exact.** OpenCV count, 11/11 seeks and freemocap reads were exact in all 18 index-pts files, also with drops and at 54,000 frames. With real VFR pts, MKV miscounts (888 for 891) and seeks miss [M] (EI:53-54, GF02).
- **MKV TimestampScale is 1 ms.** Max error 470–499 µs, and frames under 1 ms apart share a pts [M] (EI:52; RFC 9559 §5.1.2.9 per `write_throughput` FINDINGS:169).
- **The time base pitfall.** PyAV switches the stream time base from 1/30 to 1/1000 at the header. Copying it gave pts 0, 1, 2…, and VLC dropped about 87 % (12/90 PNGs). With the fix: pts 0, 33, 67, 100 and 90/90 [M] (SE §1:38).
- **Passthrough is byte-exact.**
  - No muxer changed any JPEG header. Extraction is SHA-256-identical, with no APP0/AVI1 added and no DHT inserted [M] (R `jpeg_passthrough/FINDINGS.md:152`).
  - Camera markers [M] (same file, lines 154–156):
    - C922 and C930e: `DQT SOF0 DHT DHT DHT DHT COM APP0 DRI SOS`;
    - generic camera: `APP0(JFIF) DQT DQT SOF0 DHT DHT DHT DHT SOS`;
    - all three carry the 4 standard DHTs.
  - DHT-stripped frames decode in FFmpeg [M] (lines 160–162), and `ImageDecoder` decodes stripped frames and the generic camera's frames with extra bytes after the entropy-coded data [M] (line 370).
  - So the spec must not require DHT, JFIF or a strict marker order [I].
- **MKV registers MJPEG as `V_MJPEG`, "Initialization: none"** [C] (`jpeg_passthrough/FINDINGS.md:119`). That FFmpeg writes exactly this CodecID [NV] here.
- **One SimpleBlock = one packet.** 0 laced blocks in 13 variants [M] (AS §2.1).
  - The `packet.pos + 4` offset assumes a 1-byte track number and no lacing (SE §6.6:145).
  - A track number ≥ 128 gives a 5-byte block header [C/I] (R `chromium_sync_scrub/FINDINGS.md:149-150`).
- **Room for the attachment.**
  - FFmpeg reserves 161 B for the SeekHead (`MAX_SEEKHEAD_ENTRIES 7` × 21 + 14), only for seekable, non-`live` output [C] (SE §3, `matroskaenc.c` n9.0.2 lines 77, 271, 907, 90).
  - Measured worst case: 35 B spare after our entry (4.68 GB file, 6 FFmpeg entries) [M] (SE §3 table, `big.json`).
  - Chapters set after the header add a 6th entry [M] (SE §3).
- **Unfinalised MKV in OpenCV:** FRAME_COUNT is −2.767e17 and POS_FRAMES silently returns frame 0, so "finalize before any OpenCV reader" [M] (EI:109, 120).
- **Recovered real-pts MKV** gets r_frame_rate 125/2 (62.5 fps, about 2.1× the count). Index-pts MKV recovers correctly [M] (EI:110).
- **External players.** VLC 3.0.24 plays JPEG-in-MKV at the nominal rate, not true time. A recording with drops plays shorter than the event [M] (SE §1:36). The generic camera delivers about 25.7 fps for 30 requested, so its MKV plays 14 % fast [M] (AC §4.5).
- **Rotation flag effect in other readers:** a rotation element adds 14 bytes in Tracks, and the first JPEG moves from byte 516 to 530 [M] (RF §2:42, §0). That is irrelevant now, because a flag is forbidden.

### Byte layouts

None are format-specific: Matroska defines the elements. The EBML IDs used in the prototypes (S `sidecar_embedding/append_attachment.py:13-16`, `locator.js:4-6`):

| Element | ID |
|---|---|
| EBML | `0x1A45DFA3` |
| DocType | `0x4282` |
| Segment | `0x18538067` |
| SeekHead | `0x114D9B74` |
| Seek | `0x4DBB` |
| SeekID | `0x53AB` |
| SeekPosition | `0x53AC` |
| CRC-32 | `0xBF` |
| Void | `0xEC` |
| Info | `0x1549A966` |
| SegmentUID | `0x73A4` |
| Attachments | `0x1941A469` |
| AttachedFile | `0x61A7` |
| FileName | `0x466E` |
| FileMediaType | `0x4660` |
| FileData | `0x465C` |
| FileUID | `0x46AE` |
| Cluster | `0x1F43B675` (S `sidecar_embedding/audio_offsets.py:25`) |
| SimpleBlock | `0xA3` |
| BlockGroup | `0xA0` |
| Block | `0xA1` |

### Conflicts and gaps

1. **"Nominal rate" is not defined.** Is it the requested rate (30) or the delivered rate (25.7)? The container pts and the header's nominal-rate rational depend on it [I].
   - MFR item 5 wants a nominal rate as a rational in the header.
   - Whether FFmpeg writes a consistent Matroska DefaultDuration [NV].
2. **How strict the MKV profile is.** Should the spec require the SeekHead to be the first child of the Segment, with a Void reserve, and the Segment to end at EOF? The appender needs both (`append_attachment.py:77-80`), and so do FFmpeg-written files. A file from another writer may differ [I]. Decide whether these are writer MUSTs.
3. **Chapters.** "No chapters after the header" keeps the room guarantee (SE §3). Is that a writer MUST?
4. **Track numbers.** Readers must parse the real block header (EBML walk), not assume `+4`. Writers SHOULD use track numbers < 128 [I].
5. **Other attachments.** Can an MKV carry attachments other than ours? The appender refuses a file that already has Attachments (`append_attachment.py:82`).

### Open items

- The JPEG chroma and quality definition for re-encodes (skellysync D-Q, SCOPE §7).
- 10-bit and HDR sources (D-HDR). These affect the skellysync profile only.

### Candidate tests

- **T-MKV / T-S8 (CI on pinned PyAV)** (P:374-379; SE §7.5; EP §6):
  - SeekHead + Void span − used ≥ 23 B;
  - the first packets' pts are 0, 33, 67 ms at 30 fps;
  - after `mux(i)` the file ends at frame i−1 (only while live offsets are used).
  - These check writer settings: they are writer conformance tests.
- **Profile checker on golden and writer output:**
  - one video track with CodecID `V_MJPEG`;
  - every SimpleBlock has the keyframe flag and is not laced;
  - each payload starts with SOI (`FFD8`) and ends with EOI (`FFD9`) [I];
  - pts strictly increasing, equal to `round(k·1000/fps)` ms;
  - no `Projection` element.
- **Passthrough writer test:** the extracted JPEG has the same SHA as the input (pass: 100 %).
- **OpenCV count = n_records**, and 11/11 POS_FRAMES seeks pixel-identical, on a finalised golden file (SE §5 method).
- **Reader accepts JPEGs without DHT and with trailing bytes** (golden frames). Pass: offsets and CRC check pass. The reader does not validate the JPEG markers beyond SOI/EOI.

---

## 5. Video timing sidecar

### Decided rules

**From ADR-69YS:**
1. A header, then one fixed 64-byte record per frame.
2. Each record holds: arrival, Media Foundation sample time, legacy time and fitted time (ns); JPEG offset and size in the MKV; JPEG CRC; source frame number; write index; flags; record CRC.
3. The header holds `header_size` (a multiple of 8) and `n_records`.
4. The player time never decreases within one file.
5. JS reads each i64 as two u32 halves.
6. A reader does not check every record CRC when it loads a finalised file.
7. There is no columnar or compact section.
8. The spec gives the field order, the types and the flag bits.

**From ADR-0YV1:** at finalisation the writer computes the fitted time and its flags into each record. The player uses the fitted time, or the arrival time before finalisation. The fitted time is in the sidecar, not only in a CSV.

**From ADR-CE4D item 2:** the header holds `display_rotation` in steps of 90°. The spec gives the direction.

**From ADR-M4DF:** the header holds `major`/`minor`/`prerelease` and the writer string.

**From ADR-77Z3 item 4 and P §2.7 (P:159):** the header carries the Segment UID (on disk after `start_encoding()` with `flush_packets=1`), and the offsets refer to the final bytes.

**From P row 1.5 (P:272):** the header carries "format, encoder, stable camera key and the MKV's Segment UID".

**From P row 1.4 (P:271) and EP §5 rule 7:** set `async_depth` explicitly and record it in the sidecar header with the encoder name.

**From the SL §6 spec rules:**
1. `header_size` is a multiple of 8 (64 suggested).
2. Finalisation writes `n_records`; readers fall back to the FileData size or the file length.
3. The player time must never decrease: set fit-valid for every frame or none, or have finalisation guarantee the order.
4. JS: two u32 halves minus a recording base.
5. Do not check every record CRC at load. Rely on the embed SHA for finalised files, and check per block or only for unfinalised or recovered files.

### Measured facts

- **Load cost** (SL §0, §2): 16 cameras × 1 h load in 95–107 ms at 30 fps and 166–195 ms at 60 fps. A hybrid start draws the first frame in 3–5 ms (header + first 256 records = 16.9 kB). Parsing costs about 8 ns per record [M].
- **JS record CRC check:** 210–375 ms (30 fps) and 425–767 ms (60 fps) per 16 × 1 h, about 8× the parse time [M] (SL §2:82).
- **Size:** 6.9 MB per camera-hour at 30 fps; 13.8 MB at 60 fps [M/arith] (SE §8.1; SL §1).
- **Pairing.** The T-S6 writer rule gave 100 % pairing [M] (EP §0):
  - 11,700/11,700 records with `mjpeg_qsv` in 21 runs;
  - 5,694/5,694 with turbo workers;
  - every record paired after 38/38 hard kills.
- **Gap flag.** `FLAG_GAP` count = `source_frame_number` gaps in all runs [M] (EP §2.2). An injected encode failure shows only as `FLAG_GAP`, so EP recommends a distinct "encode skip" flag [M/I] (EP §3).
- **Clock definitions** (TAO:398, §6.2):
  - arrival = `perf_counter_ns` (QPC) [C] (pymf `mf.py:44`);
  - MF sample time = the raw `ReadSample` timestamp in 100 ns units (×100 → ns). It shares the QPC timebase [M]: arrival − sample time is bimodal at about 0.3–1 ms or about 16 ms;
  - the generic camera has a 32 ms sample-time shift [M];
  - fit the lattice on arrival, with slots from sample time [M] (TAO:394-395).
- **What the fitted time means.** The lattice is fitted on the lower envelope of the stamps. It "stands in for capture time up to a constant" (TAO:248) and includes each model's unmeasured latency (TAO:273) [C/M]. So the fitted time is not capture time.
- **Legacy time.** Today's `timestamp.perf_counter_ns.ns` is the midpoint of pre-grab and post-grab [C] (RFF:20, citing `create_camera_csvs.py:50-58`). P row 1.6 says "today's stamp computed as now" with the MF backend.
- **Stale stamps.** A fit on stale stamps "fits the loop, not the camera" and can report `fit_unreliable: false` wrongly [M] (TAO:318).
- **Fit accuracy:** ≤ 0.56 ms against a flash in one 30 s run; today's stamps are off by 4.6–16 ms [M] (P row 1.6).
- **Recommended player rule.** Pick frames by PREV in integer ns on one shared clock; show nothing before the first frame; hold with a stale flag in gaps; stop at a hold limit of about 1.5P [I] (EI:381). PREV/NEAREST gave 0 mismatches in 48/48 cells [M] (EI:376).

### Byte layouts

**Record, 64 B, little-endian. Proposed in SE §8.1 (lines 190–204) [I]; implemented in S `encoder_pairing/eplib.py:35-41`. This is a prototype: the field order is not decided by any ADR.**

| Bytes | Field | Type | Notes (SE §8.1) |
|---|---|---|---|
| 0–7 | `arrival_ns` | i64 | host monotonic (QPC on Windows) |
| 8–15 | `sample_time_ns` | i64 | MF sample time × 100; INT64_MIN when absent |
| 16–23 | `legacy_ns` | i64 | today's stamp |
| 24–31 | `fitted_ns` | i64 | INT64_MIN until finalisation |
| 32–39 | `offset` | u64 | JPEG start in the MKV; live value provisional |
| 40–43 | `size` | u32 | |
| 44–47 | `jpeg_crc32` | u32 | zlib CRC-32 of the JPEG bytes |
| 48–51 | `source_frame_number` | u32 | camera/capture sequence; gaps = drops (eplib masks `sfn & 0xFFFFFFFF`, line 53) |
| 52–55 | `write_index` | u32 | 0..N−1 = recording frame number = container pts |
| 56–59 | `flags` | u32 | |
| 60–63 | `record_crc32` | u32 | over bytes 0–59 |

eplib spells it as `REC_BODY = "<qqqqQIIIII"` plus `"I"` (lines 35–37).

**Flag names and bits differ between sources** (all prototype or proposal):

| Source | Flags |
|---|---|
| SE §8.1:203 | gap, repeat, PTS bumped, fit valid, fit unreliable, offset final (no bit numbers) |
| `eplib.py:46-49` | `FLAG_GAP=1`, `FLAG_OFFSET_LIVE=2`, `FLAG_OFFSET_TAIL=4` (last record found by a tail search after `close()`), `FLAG_RECOVERED=8` |
| EP §3, §5 rule 2 | adds "encode skip" |
| P row 1.6 | drop/repeat flags, `fit_unreliable` |
| S `python_integration/recwriter.py:46-47` (older 48 B prototype) | `FLAG_PTS_ADJUSTED=1`, `FLAG_FRAME_GAP=2` |

**Header proposal, SE §8.1 (lines 179–188) [I]:**
- the fixed part: magic `SKFR`, `version`, `header_size`, `record_size`, flags; Segment UID (16 B, zero until known); stable camera key; format fourcc; width; height; nominal rate as a rational; encoder and quality setting; host clock id (QPC / `CLOCK_MONOTONIC` / `mach_absolute_time`) and its frequency; a (host ns, UTC ns) anchor pair taken at start;
- then a length-prefixed UTF-8 JSON block: controls, producer and version, and skellysync source and sync fields.

**Other prototype headers:**
- `eplib.py:42`: see §3.
- S `python_integration/recwriter.py:32-36`, the "prototype's 48 B" that SE S1 rejected:
  - magic `SKCAMFR1`;
  - header `"<8sIIII4sIIq20x"` = magic, version, header_size, width, height, codec fourcc, tb_num, tb_den, t0_ns, pad = 64 B;
  - record `"<qqqIIIII"` + CRC = frame_number, timestamp_ns, pts, size, packet_crc32, flags, write_index, reserved, record_crc.
- S `sidecar_load/gen.py:73-87`: a synthetic 512 B header that SL §1 says "is not the spec header". Ignore it.

**Candidate header fields from MFR (lines 16–33):**
- MUST:
  1. Segment UID;
  2. version triple + writer string;
  3. `camera_label` (today's short camera id; freemocap's key);
  4. `display_rotation` ∈ {0, 90, 180, 270}, with skellysync `rotation_applied`;
  5. nominal rate as a rational;
  6. `time_base` kind (host monotonic, or a synthetic aligned timeline for skellysync); files of one take that say "host" MUST share one clock;
  7. the discovery rule.
- SHOULD:
  8. `take_uuid`;
  9. `group_size`;
  10. take anchor `{take_start_host_ns, take_start_utc_ns, utc_offset_min}`;
  11. stable camera key, stored hashed.
- Optional: `group_position`, `camera_name` (MFR A table).

### Conflicts and gaps

1. **The header field list is not decided.**
   - ADR-69YS names only `header_size` and `n_records`.
   - P row 1.5 adds format, encoder, stable camera key and UID; P row 1.4 adds `async_depth`; ADR-CE4D adds `display_rotation`; ADR-M4DF adds the version triple and the writer string; MFR adds items 3–11.
   - MFR §F:142 notes that ADR-69YS lists none of the row 1.5 fields. ADR-69YS item 8 leaves the order, types and flags to the spec, so the draft decides them.
2. **The stable camera key.**
   - P row 1.5 says "stable camera key". P row 2.6 says "serial, else port path" (raw, phase 2).
   - MFR O4 (lines 108–111) recommends a 64-bit truncated SHA-256 of a kind-tagged string over vid, pid and serial (or port path), with `camera_label` kept as the short id.
   - Today's `camera_id` is a 16-bit truncated SHA-256 of the device path, with about 0.2 % collision chance at 16 cameras [C/I] (MFR B table, `detect_cameras_devices.py:44-54`).
   - Which field holds which identity is open (see decision 6).
3. **Fit validity per frame against monotonic time.**
   - ADR-0YV1 and SE S2: use the fitted time when "fit valid", else arrival.
   - TAO:493 and P row 1.6: a per-frame `fit_unreliable` flag that falls back to the raw time.
   - SL §6.3: a mid-file switch can step back by about the arrival jitter and breaks the PREV binary search, so set fit-valid for all frames or none, or have finalisation guarantee the order.
   - ADR-69YS item 4 requires monotonic time. The spec must say which time the player uses per frame and how finalisation keeps it monotonic, for example: "if any frame is not fit-valid, the player uses arrival for the whole file", or "finalisation writes `fitted_ns` for every frame, using segment fits; `fit_unreliable` is informative only" [I].
4. **Where the fitted time comes from (definition).** Fitted on arrival with slots from sample time (TAO), so it carries the transport latency. The spec must define it as "the writer's best estimate on the host clock", not as capture time [I].
5. **Time fields for producers without live capture.**
   - skellysync: the source pts are on no host clock. MFR item 6 proposes a "synthetic aligned timeline" kind.
   - The converter: old CSV `timestamp.perf_counter_ns.ns` (the legacy midpoint).
   - What goes in `arrival_ns`, `sample_time_ns` and `legacy_ns` for them is undefined.
6. **skellysync per-record fields do not fit the fixed 64 B record.** SCOPE §2.8 asks for `source_frame_index` (u64) and `source_pts_ns` (i64) per record. Options:
   - map them onto `source_frame_number` (u32) and `sample_time_ns`;
   - a second table;
   - a larger `record_size` in a skellysync profile.
7. **`legacy_ns` is skellycam-specific** (it exists to keep the old CSV columns, P row 1.6). Is it a format field with defined meaning, or "writer-defined; INT64_MIN if none"?
8. **No stored whole-sidecar checksum exists.** SL §6.5 says "rely on the embed SHA for finalised files", but ADR-77Z3 checks the SHA only at embed time, and Matroska stores no hash (FileUID is random, `append_attachment.py:102`). A reader cannot verify a finalised sidecar without per-record CRCs (see decision 11).
9. **CRC failure handling.** `eplib.read_sidecar` stops at the first bad CRC (`eplib.py:70-72`). FS §7 says "drop a trailing partial record and any record whose CRC fails". Stop, or skip? (See §11 and decision 9.)
10. **Header CRC.** It exists in `audio_skellycam/pipeline.py:45` (.skau) but not in eplib. Finalisation rewrites header fields (`n_records`, UID) in place.
11. **JSON block in the header.** SE §8.1 and AC §4.2 propose one. MFR O2(iii) warns that an opaque writer-extension block couples writer data to the format bytes. Decide whether normative fields may live in JSON.
12. **The first read must find `header_size`.** The hybrid load reads the header plus 256 records (SL §7), so `header_size` must be at a fixed early offset [I].

### Open items

- The clock id values for Linux and macOS (T-S7, SE §8.3; Linux/macOS timing tests): provisional.
- The `async_depth` value (TP3) does not change the layout.

### Candidate tests

- **Record codec round trip** on the golden sidecar, in Python and JS. Pass: every field equal. This includes INT64_MIN sentinels and offsets above 2^32 (generated synthetic records up to 41 GB offsets, as SL §1).
- **JS u32-halves conversion** of i64 values near ±2^53 and INT64_MIN. Pass: exact or flagged as sentinel.
- **`header_size % 8 == 0`** and records 8-aligned (writer test).
- **Player time is monotonic** over every golden file (fit valid, fit absent, mixed). Pass: non-decreasing.
- **Player-time selection rule** on the mixed-fit golden file. Pass: the selected time series equals the expected one.
- **`FLAG_GAP` set iff `source_frame_number` ≠ previous + 1** (writer test, EP §2.2).
- **The encode-skip flag** appears on the next record after an injected encoder failure (EP §3 injection).
- **Pairing (T-S6 method, EP §0):** JPEG CRC at the offset; a barcode equal to `source_frame_number`; times equal to the truth; `write_index` = position; the container packet with pts = `write_index` has the same CRC and offset. Pass: 100 %. This is a writer conformance test with a generated barcode source.
- **`n_records` written at finalisation** equals the record count. The reader falls back when `n_records` = 0 (live file).

---

## 6. Audio: FLAC in `.mka` (skellycam)

### Decided rules

1. FLAC is the audio codec. Opus needs a new entry (ADR-CA03 item 1).
2. skellycam records to a native `.audio.flac` while recording. At finalisation it stream-copies the FLAC frames into `<rec>.audio.mka` and appends the `.skau` as an attachment (ADR-CA03 item 2).
3. The player decodes FLAC packets by byte offset with WebCodecs `AudioDecoder`, finding them in the packet table (ADR-CA03 item 4).
4. Delete the native `.flac` only after every FLAC frame CRC and the decoded sample count of the `.mka` match (ADR-77Z3 item 3; P S9).
5. Do not give a native `.flac` to a player as the final file (ADR-CA03 "Not repeated").

**Recording settings** (writer and skellycam settings, perhaps outside the format):
- native FLAC with `frame_size=1024` and `flush_packets=1`;
- 48 kHz on the WASAPI entry;
- a dedicated audio process.
- Sources: P §2.8 (P:182-184); FS §5.1.

### Measured facts

- **Crash loss.** Native FLAC with `frame_size=1024`: 0 ms lost in 12/12 hard kills [M] (AC §2.2).
- **Live offsets.**
  - Packet i sits at header length + the sum of earlier packet sizes (1,408/1,408), and after `mux(i)` the file ends exactly at packet i, with no hold-back [M] (FS §1).
  - The header is 8,286 B: STREAMINFO 34, VORBIS_COMMENT 44, PADDING 8,192 [M].
  - The final encoder flush returns one **empty** packet (1,408 encoder packets against 1,407 frames), so the index must skip zero-size packets [M] (FS §1:30).
- **Stream copy into `.mka`:**
  - frames byte-identical (1,407/1,407);
  - CodecPrivate 42 B = `fLaC` + STREAMINFO; CodecID `A_FLAC`; 0 laced blocks;
  - decoded = source in PyAV and ffmpeg; ffprobe duration 30.000 s [M] (FS §3).
- **VLC 3.0.24** drops the last 1,280 samples (26.7 ms) of a native `.flac`, and plays the `.mka` complete and sample-exact [M] (FS §4).
- **WebCodecs decode** with `AudioDecoder('flac', description = CodecPrivate)`: E45 is sample-exact; E35 is within 1.56e-5 (about half a 16-bit step, a conversion difference); cold start at packet 700 works [M] (FS §4). FLAC without `description` throws or fails [M] (AS §3).
- **Killed `.flac` files:** STREAMINFO total samples = 0 and MD5 zero. They still decode, and stream-copy into `.mka` without patching [M] (AC §2.2; FS §3).
- **Size:** about 172 MB/h mono on synthetic audio [M] (AC §1.3). Real microphones [NV].

### Byte layouts

None of our own. FLAC (RFC 9639) and Matroska `A_FLAC` (CodecPrivate = `fLaC` + STREAMINFO) define them.

### Conflicts and gaps

1. **Is the native `.audio.flac` part of the format?** It exists only while recording or after a crash, and the README scope does not list it. The recovery rules (§11) need it named, with its live sidecars.
2. **Recommended reader rule:** do not trust STREAMINFO total samples (0 after a crash, carried into the `.mka` by the stream copy); use the packet table [I].
3. **Constraints a writer must meet,** not yet stated: one FLAC track; sample rate (48 kHz for skellycam?); channels; bit depth; blocks unlaced; one SimpleBlock = one FLAC frame.

### Open items

- FLAC size on real audio [NV].
- Linux/macOS audio timing.

### Candidate tests

- **Stream copy keeps bytes:** every FLAC frame in the `.mka` equals the `.flac` frame (golden pair). Pass: n/n.
- **Decoded sample count of the `.mka`** = the sum of `n_samples` in the packet table = the decoded native `.flac`.
- **Profile check:** one track; `A_FLAC`; CodecPrivate starts with `fLaC`; SimpleBlocks unlaced.
- **Writer deletes the `.flac` only after verification:** inject a CRC mismatch. Pass: the `.flac` is kept.
- **Reader handles STREAMINFO total = 0** (recovered golden `.mka`). Pass: the duration comes from the packet table.

---

## 7. Audio timing sidecar (`.skau`) and the packet table

### Decided rules

- The packet table lives in the `.skau` for skellycam (ADR-CA03 item 4).
- The `.skau` is appended to the `.mka` the same way as the video sidecar, and the separate file is deleted after a verified embed (ADR-77Z3 items 1 and 2; P D16).
- The header holds the version triple and the writer string (ADR-M4DF).

**Content, from P §2.8 (P:185-188):**
- one 48 B record per callback block (host ns, PortAudio ADC ns, sample index, flags, CRC);
- a live packet record per FLAC frame;
- after a kill, the records match the bytes on disk, with at most one unindexed frame.

**Finalisation, from P:189-194 and FS §5.2:**
1. stream-copy into `.mka`;
2. scan it and check the CRCs against the live packet records;
3. write the packet table (with `.mka` offsets) and the drift fit into the `.skau`;
4. append the `.skau`;
5. verify the frame CRCs, the decoded sample count and the attachment SHA, then delete the `.flac`.

### Measured facts

- **Clock.** PortAudio time = `perf_counter` (QPC) on Windows (0 ± 7 µs): the same timebase as the video sidecar [M] (AC §4.1).
- **ADC time** behaves like the end of the block: fit x = `sample_index + frames` [M/I] (AC §4.1, §4.3 step 1).
- **MME:** `currentTime` = 0 and ADC time alternates 0 / 23.2 ms. Unusable, so store INT64_MIN [M] (AC §4.1, §4.2).
- **Drift.**
  - Microphones are within about ±10 ppm of QPC, which is 36 ms/h [M].
  - One microphone stepped about 9 ms at 6–8 s.
  - So use change-point segments, not a fixed start-up exclusion [M] (AC §4.1).
- **Mapping** (AC §4.3) [I/M]:
  - segment fit t = t0 + (n − n0)·1e9/f_eff;
  - per segment store n0, t0, ppm and residual p99;
  - `fit_unreliable` when p99 > 5 ms or the segment is shorter than 10 s;
  - split segments at residual jumps > about 3 ms;
  - frame → sample: n = n0 + (T − t0 − latency)·f_eff/1e9;
  - latency = a per-microphone `audio_latency_ns` from the clap test (TP2 A3). PortAudio reports 42.7–46.4 ms (unchecked).
- **Old start anchor** makes audio 9–74 ms early [M] (AC §4.1). The fit removes the error.
- **Size:** 48 B timing + 32 B packet record per block is 13.5 MB for a 1-hour `.skau`. Appended, it leaves 75 B spare [M] (FS §3). The timing records alone are 8.1 MB/h (AC §4.2).
- **The prototype's 40 B record** had 0 bad CRCs in 7 runs [M] (AC §4.2).

### Byte layouts (all prototypes; none decided)

**Timing record, 48 B, proposed in AC §4.2 (lines 170–182) [I]:**

| Bytes | Field | Type | Notes |
|---|---|---|---|
| 0–3 | `block_index` | u32 | |
| 4–7 | `frames` | u32 | |
| 8–15 | `sample_index` | i64 | the block's first sample |
| 16–23 | `host_ns` | i64 | `perf_counter_ns` at callback entry |
| 24–31 | `pa_adc_ns` | i64 | INT64_MIN when the host API gives 0 (MME) |
| 32–39 | `pa_current_ns` | i64 | |
| 40–41 | `flags` | u16 | overflow / underflow, queue drop (silence written), priming |
| 42–43 | reserved | | |
| 44–47 | `crc32` | u32 | over bytes 0–43 |

**Timing record, 48 B, in the kill test** S `flac_skau/terminate_kill.py:53-54`, `TIM_SIZE` at :33: `struct.pack("<Qqqq", i, b0, perf_counter_ns, time_ns)` = block u64, first_sample i64, two clocks i64; then CRC32 u32 over bytes 0–31; then 12 B pad. **This differs from AC §4.2.**

**Older timing record, 40 B,** S `audio_skellycam/pipeline.py:35-37`: `REC_FMT = "<IIqqqHH"` + CRC32 = block index, frames, sample index, host ns, ADC ns, flags, reserved. Flags: `F_PA_INPUT_OVERFLOW=1`, `F_PA_INPUT_UNDERFLOW=2`, `F_QUEUE_DROPPED_SILENCE=4`, `F_PRIMING=8`.

**`.skau` header proposals:**
- AC §4.2 (lines 164–169) [I]: magic `SKAU`, version, header_size, record_size, flags; recording UUID (16 B); device and encoder rate; channels; nominal block; clock id (1 = QPC) and frequency; a (host ns, UTC ns) anchor; then length-prefixed JSON (device, host API, PortAudio version, `stream.latency`, codec settings, versions).
- `pipeline.py:33`: `"<4sHHHH16sIIHHBxxxQqq"` = magic 4, version u16, header_size u16, record_size u16, flags u16, recording uuid 16 s, device rate u32, encoder rate u32, channels u16, nominal block u16, clock id u8 (1 = QPC), 3 pad, clock freq u64, anchor host ns i64, anchor utc ns i64 = 68 B, + CRC32 = 72 B (`header_size` = 72, line 43).
- `flac_skau.py:155`: `b"SKAU" + "<HHII"(version=1, header_size=64, record_size=48, flags=0)` + 48 random bytes = 64 B. Its payload is header + 48 B × n_blocks + the packet table (lines 154–158), with **no field giving the table offset or count**.

**Packet record, 32 B, final table.** `flac_skau.py:157` `"<QIIqII"`, which matches AS §4 (lines 151–160):

| Bytes | Field | Type | Notes |
|---|---|---|---|
| 0–7 | `offset` | u64 | |
| 8–11 | `size` | u32 | |
| 12–15 | `n_samples` | u32 | |
| 16–23 | `first_sample` | i64 | after the codec delay (Opus starts at −312) |
| 24–27 | `crc32` | u32 | frame CRC |
| 28–31 | `flags` | u32 | keyframe, discard padding, last |

**Packet record, 32 B, live.** `terminate_kill.py:31`: `PKT = struct.Struct("<QIqII4x")` = offset u64, size u32, first_sample i64, frame_crc u32, record_crc u32 (over the first 24 B), 4 B pad. **It has no `n_samples` and no flags, and it adds a record CRC.**

**Older live index, 16 B,** `flac_skau.py:74`: `"<QII"` = offset, size, crc.

### Conflicts and gaps

1. **Three different 48/40 B timing layouts,** with different CRC coverage (bytes 0–43 or 0–31) and different fields: AC has `pa_current_ns`, `frames` and flags; terminate_kill has a UTC clock and no flags. P §2.8 describes the AC fields.
2. **Two different 32 B packet records.** The final table has `n_samples` and flags but no record CRC. The live record has a record CRC but no `n_samples`. A torn-tail check on live files needs a record CRC (FS §7). The finalised table could rely on the attachment, but then decision 11 applies.
3. **One live file or two?**
   - The prototype used two live files: `<rec>.skau.live` (timing) and `<rec>.pkt.live` (packets) (`terminate_kill.py:9-14, 89`).
   - P §2.8 says "the `.skau` timing records … plus a live packet record per FLAC frame".
   - AC §0 names the file `<rec>.audio.skau`.
   - One file would need a record-type tag [I] (see decision 3).
4. **The header must give the table's position and count:** `packet_table_offset` and `packet_record_count`, as AS §4 proposes for the camera sidecar. The prototype header has neither.
5. **Packet-table offsets point into different files.**
   - Live packet records point into the `.flac`; final ones point into the `.mka` (FS §5.2 step 3).
   - The header must say which (for example a flag "offsets refer to the .mka, final") [I].
   - The "skip zero-size packets" rule must be stated (FS §1:30).
6. **Binding the `.skau` to its file.**
   - ADR-77Z3 item 4 says "offsets and Segment UID in a sidecar refer to the final bytes", which implies the `.skau` carries the `.mka` Segment UID.
   - A native `.flac` has no Segment UID, so a live `.skau` cannot bind by UID. Use `take_uuid` and the file name until finalisation [I].
   - AC proposed a "recording UUID", with the Opus tag `SKELLYCAM_RECORDING_ID`. That is now obsolete with FLAC; MFR wants `take_uuid`.
7. **Where the drift-fit segment table goes,** and its layout: n0, t0, ppm, residual p99, `fit_unreliable` per segment (AC §4.3). This is undefined, and provisional until the drift test.
8. **`audio_latency_ns`:** where it is stored and who supplies it (a per-microphone clap test, TP2 A3). Provisional.
9. **Write order.** The prototype writes the timing record **before** the FLAC frame, and the packet record **after** it (`terminate_kill.py:9-13`; AC §4.2:185 says "each record is flushed before its block is encoded"). The spec should fix this order, because the recovery rules depend on it (§11) [I].

### Open items (provisional, per open-work.md)

- The drift fields: waits for the audio clock drift test A4.
- The Linux/macOS clock ids and ADC semantics: waits for the Linux/macOS audio timing test.
- The latency field: waits for the clap test A3.

### Candidate tests

- **Codec round trip** of timing records, the packet table and the header (golden `.skau`) in Python and JS.
- **Packet table check:**
  - every packet record's offset/size/CRC matches the `.mka` bytes;
  - the sum of `n_samples` = the decoded samples;
  - `first_sample` is contiguous;
  - no zero-size entries.
- **Packet table built at finalisation** equals an EBML scan of the `.mka` (AS §2.1 method).
- **WebCodecs decode by offset** from the golden `.mka` + `.skau`. Pass: samples equal to the reference (E45 exact; E35 within 1.6e-5), including a cold start at packet k.
- **Frame → sample mapping** on a golden file with a known fit. Pass: n within ±1 sample of the formula. Provisional.

---

## 8. Audio in the camera MKV (skellysync)

### Decided rules

- skellysync writes one FLAC track into each camera MKV, in the same pass as the video. There is no remux (ADR-CA03 item 3; SCOPE §2.6 "Decided 2026-11-12").
- FLAC at the source rate, keeping the source channels (P §2.8:205).
- **The audio window equals the video window, in samples** (P:211).
- The packet table lives in the camera sidecar (ADR-CA03 item 4).
- Offsets and the UID are rebuilt by scan after the audio step (SE §6.7).

### Measured facts

- Live offsets break with FLAC in the same pass: 0/1,799 [M] (SE §6.5).
- **Scan:** matched every video (450/450) and audio (157/157 FLAC) CRC in 8–17 ms. 0 laced blocks [M] (AS §2.1).
- **External readers:** VLC plays in sync and seeks to the exact slot; FLAC has 0 offset. OpenCV count and seeks are unchanged [M] (AS §2).
- **OpenCV frame count** comes from the longest track. With FLAC the audio overhang is −0.3 to 0.7 ms, and the count was correct 20/20 at 30, 60 and 120 fps. Rule: the audio must not overhang the video [M] (AS §2.3).
- **WebCodecs details:**
  - WebCodecs ignores DiscardPadding, so the player stops at `total_samples`;
  - E35 clamps negative chunk timestamps, so place audio by sample index, not by `AudioData.timestamp` [M] (AS §3);
  - FLAC CodecDelay and SeekPreRoll are 0 [I/M].
- **Interleave.** Per frame k: encode samples `[round(k·rate/fps), round((k+1)·rate/fps))` with pts = sample index at time base 1/rate, mux them, then mux JPEG k (pts = k, time base 1/out_fps). N = `round(frame_count × rate / out_fps)` [C] (AS §5.1).
- **Bit depth.** 24-bit roughly doubles the size and adds nothing for decoded AAC, so use 16-bit [M/I] (AS §1.2). 44.1 kHz is kept as is [M] (AS §1.3).
- **Latent lag bug:** video lag = audio lag + (audio_start − video_start) (AS §5.2). This is a skellysync implementation fix.

### Byte layouts

The same 32 B packet record as §7 (AS §4: offset u64, size u32, n_samples u32, first_sample i64, crc32 u32, flags u32), placed **after the per-frame records**. The header gives `audio_table_offset` and `audio_record_count`. Size: 1.2 MB per camera-hour for FLAC [arith].

The header JSON `audio` block proposal [I] (AS §4:142-149):
- `track_number`, `codec_id`, `webcodecs_codec`, `sample_rate`, `channels`, `channel_layout`;
- `codec_private` (base64);
- `codec_delay_samples`, `seek_preroll_samples`, `total_samples`;
- `first_sample_offset_ns` (0 by construction);
- `encoder` and its settings;
- `source{stream_index, codec, sample_rate, channels, start_minus_video_start_ns, window_first_sample, pad_front_samples, pad_back_samples, resampled_from, resampler}`.

### Conflicts and gaps

1. **JSON or fixed fields.** The audio block proposal is JSON. If normative fields must be fixed binary (decision 4), then `track_number`, `sample_rate`, `channels`, `total_samples` and `codec_private` need fixed fields or a defined sub-block.
2. **The packet table after the frame records** means the video records are not at the end of the sidecar. A live skellysync sidecar does not exist (Design A writes after the pass), so this is OK [I]. Still, the spec must define the section offsets.
3. **Channels above 2:** downmix or refuse is undecided (AS §1.3, §8.2).

### Open items

skellysync camera sidecar header (D-Q, D-FPS, D-HDR, D-DRIFT): see §14.

### Candidate tests

From AS §6 (lines 192–199):
1. A burst fixture (frame index in pixels, irregular flashes, distinct L/R). Pass: 0-sample A/V error, channels kept, frames exact.
2. A source whose video starts after its audio; a 44.1 kHz source.
3. R1 60→30 with bursts on dropped frames.
4. cv2 count = `frame_count` at 30, 60 and 120 fps.
5. Scan: all CRCs match; `total_samples` = the decoded count; embedding changes nothing.
6. A stereo source plus a mono analysis signal stays stereo.

Also: **the audio does not overhang the video:** last audio sample time ≤ video end (writer test).

---

## 9. Embedding and finalisation

### Decided rules

From ADR-77Z3, P §2.7 and P D16:
- At finalisation, append the video sidecar to the camera MKV as a Matroska attachment **at the end of the file**, and the `.skau` to the `.mka` the same way.
- Delete a separate sidecar only after the embed verifies: the attachment SHA matches and the media blocks did not change.
- Never use `ffmpeg -attach`. It puts Attachments before the Clusters, and the first JPEG moved from byte 550 to 5,468 [M].

**Finalisation order for every producer** (SE §7.3; P:160):
1. any remux or audio mux;
2. rebuild every offset by scanning the final MKV, checking each frame's CRC;
3. write the final UID;
4. (timestamp CSVs: skellycam only, not the format);
5. embed.

The fitted times are written at finalisation too (ADR-0YV1). The audio order is in §7.

### The appender procedure

From S `sidecar_embedding/append_attachment.py:1-10, 68-117`; SE §2:44-49:
1. Parse the EBML header, the Segment header, the first SeekHead and the Void after it.
2. Append `Attachments{AttachedFile{FileName, FileMediaType, FileUID, FileData}}` at EOF. FileUID is 8 random bytes, never 0 (line 102). Then `fsync`.
3. Rewrite the 8-byte Segment size in place, at the same width (line 111), then `fsync`.
4. Rewrite the SeekHead with one more Seek entry (SeekID = Attachments, SeekPosition relative to the Segment data start) inside the old SeekHead + Void span:
   - keep the CRC-32 element if it was there (lines 91–93);
   - if the leftover is exactly 1 byte, widen the SeekHead size field by one byte (lines 96–97);
   - otherwise pad with a Void (2-byte minimum);
   - then `fsync` (line 113).
5. **It refuses:**
   - an unknown-size Segment (a crashed file);
   - a Segment that does not end at EOF;
   - a first Segment child that is not a SeekHead;
   - a file that already has Attachments;
   - no room in the SeekHead span (lines 77–82, 98).

### The locator (head-anchored reader)

From S `sidecar_embedding/locator.js:25-96`; SE §4; RT §7:
- **Read 1:** 4,096 B at offset 0 (EBML header, DocType `matroska` or `webm`, Segment, SeekHead, and Info with the SegmentUID when Info falls inside this read).
- **Read 2:** 512 B at the Attachments position.
- **Read 3:** the FileData.
- It matches by FileName and/or FileMediaType (line 87). It never walks Clusters.
- Arithmetic uses `v*256+b` (exact to 2^53).
- **Failure reasons:** `not-ebml`, `no-segment`, `no-seekhead` (crashed file), `no-attachments-entry`, `attachments-past-eof`, `stale-seekhead`, `unknown-size-attachedfile`, `short-filedata`, `no-matching-attachedfile`.
- **Wrapper changes recommended in RT §7:** return an empty array for 416 or a past-EOF throw; check that a 206 `Content-Range` start equals the request.

### Measured facts

- **Only 25–26 header bytes change,** all inside the first 155 bytes. Frames do not move. VLC, ffprobe and OpenCV 5.0.0 read the file as before (OpenCV 11/11 seeks) [M] (SE §2, §5).
- **After an append:** frames unchanged = same (pos, size, pts) and identical JPEG bytes. On 4.68 GB files, the SHA-256 of every byte after the SeekHead + Void span was unchanged, with 5,614 frames past 4 GiB [M] (SE §3:81).
- **Locator:** 3 reads; 2.2–5.5 ms under `file://` in E35/E45; FileData at 4,680,533,554 found in 1.7 ms [M] (SE §4). The same 3 reads work through `protocol.handle` and through HTTP 200-without-size [M] (RT §7).
- **Append time:** 20 ms for 5.2 MB; 557–657 ms for 4.4 MB on a 4.68 GB file, mostly the fsyncs [M/I] (SE §3:82).
- **`.mka` SeekHead spare:** 91 → 75 B after the append. Blocks and the UID are unchanged [M] (FS §3).
- **skellysync:** embed in 5.5–7.5 ms; blocks unchanged (1,201/1,201 Opus and 607/607 FLAC); UID kept [M] (AS §2 note 5, §5.1).

### Conflicts and gaps

1. **Is embedding optional?** SE §7.3 says "optionally embed". ADR-77Z3 and D16 make it the rule. What if the appender refuses (no room, or a file from a third-party writer)? Proposal: keep the separate sidecar as the final form, a SHOULD-level fallback [I] (decision).
2. **Interrupted embed is not covered.** With the write order append → Segment size → SeekHead:
   - **Crash after step 2:** trailing bytes outside the Segment. The locator gives `no-attachments-entry`, and the appender then refuses ("Segment does not end at EOF").
   - **Crash after step 3:** the Segment includes an unreferenced Attachments element, and the appender would append a second one.
   - The separate sidecar still exists (it is deleted only after verify), so the recovery rule can be: "truncate unreferenced trailing Attachments, or bytes after the Segment, then re-embed" [I] (decision 12).
3. **The verify procedure needs a definition:**
   - the SHA-256 of the attachment's FileData equals the payload (FS §3 uses ffmpeg `-dump_attachment`);
   - "media blocks unchanged" = for each block, the (offset, size, CRC) is equal before and after, or the SHA of every byte after the SeekHead span is equal (the SE big-file method).
4. **Precedence when both the embedded and the separate sidecar exist** (only in the crash window between embed and delete, or after a failed verify):
   - SE §7.4: "Use the separate sidecar when it exists; otherwise run the locator."
   - MFR item 7: "embedded wins over separate".
   - P row 1.9: "use a separate sidecar only for unfinalised or crashed files".
   - **These conflict.** Recommendation: the embedded copy wins when its UID matches; else the separate copy when its UID matches; else rebuild by scan [I] (decision 13).
5. **The order of the fitted-time write and `n_records`** relative to the UID write is not stated. All must come before the embed, and the record CRCs must be recomputed after the in-place fitted writes [I].
6. **The manifest write** must come after every file of the recording is finalised (ADR-5PP8 item 3). Its place in the order is not stated.

### Candidate tests

- **Appender:**
  - On golden finalised MKVs (no tags; tags; chapters at the header; generated large file): only bytes within the SeekHead + Void span and the Segment size change; all block (offset, size, CRC) are equal; the extracted FileData SHA equals the payload; ffprobe frame count unchanged.
  - Refusals: unknown-size Segment, trailing bytes, existing Attachments, no room. Pass: an error and the file unchanged (SHA).
- **Locator in JS and Python** (SE §4 table):
  - appended file: ok, 3 reads;
  - plain file: `no-attachments-entry`;
  - crashed file: `no-seekhead`;
  - a SeekHead pointing at the wrong element: `stale-seekhead`;
  - FileData above 4 GiB: ok. A generated sparse file, or a test that is skipped when there is no room on disk.
- **Interrupted embed** (generated states after step 2 and after step 3). Pass: recovery yields a valid single attachment, and the media blocks are unchanged.
- **Finalisation order:** after finalisation the sidecar has `offset final` on every record, the UID equals the MKV's, the fitted times are present, and the separate sidecar is deleted only after verify. Inject a verify failure; pass: the separate sidecar is kept.
- **T-S10:** the golden MKV + sidecar (separate and embedded) reads identically in the Python and JS readers (SE §8.3; P:378).
- **External compatibility after embed:** OpenCV count and 11/11 seeks unchanged; ffprobe count unchanged (SE §5). VLC is optional and local only.

---

## 10. Segment UID, live offsets and final offsets

### Decided rules

- **The Segment UID is in the sidecar header.** It is on disk right after `start_encoding()` with `flush_packets=1` (P:159; SE §6.2).
- **The offsets and the UID refer to the final bytes** (ADR-77Z3 item 4).
- **The player rejects a sidecar whose UID does not match the file** (P:161, row 1.9).
- **After a remux, rebuild the offsets by a scan of the final bytes** (ADR-77Z3 "Not repeated").
- **Writer rule for live offsets** (P row 1.5; EP §5 rules 1–5):
  1. `seq` is a gap-free submit counter, and the only identity that passes through the encoder (`frame.pts = seq` at time base 1/fps for `mjpeg_qsv`; never ns pts or `copy_opaque`).
  2. A pending map is keyed by `seq`.
  3. Packets are released strictly in `seq` order.
  4. `write_index` = packets muxed so far = container pts.
  5. **Record k is written after `mux(k+1)` returns,** with `offset = st_size − size_k` (provisional flag). The last record is written after `close()` (tail search) or at finalisation (scan).
  6. `encode(None)` is called once per recording.
- **Live offsets only for a video-only MKV.** They break with FLAC in the same pass (P:154; SE §6.5). skellysync uses no live offsets (AS §2.1).
- **Finalisation rebuilds every offset by scan** (P row 1.5; SE §7.3).
- **Keep live offsets:** they are cheap (ST "Consequence").

### Measured facts

- **One-behind rule:** after `mux(i)` the file ends at frame i−1: 89/89 and 2,699/2,699 [M] (SE §6.1). With `flush_packets=0` this fails (0/89).
- **Cost:** `os.stat` per mux is 23.7–24.9 µs p50, 382–566 µs p99.9, 0.93 ms max at 16 × 1080p60. Each sampled offset pointed at an SOI [M] (ST).
- **Any remux gives new offsets and a new UID:** 0/1,800 offsets kept; the UID changed from cc82… to fcc5… [M] (SE §2, §6.7).
- **Scan cost** (18,000 frames, warm cache): EBML walk 112–116 ms; PyAV `pos+4` 63–86 ms; exact 18,000/18,000 [M] (SE §6.6). Cold cache and HDD: T-S3 [NV].
- **The UID** was unchanged from `start_encoding()` to `close()` in 2/2 files [M] (SE §6.2).
- **The locator reads the UID from Info** in the first 4 KB of FFmpeg files (locator.js:52-59).

### Byte layouts

- **SegmentUID:** 16 bytes in Info (Matroska).
- **Text encoding:** the prototypes use lowercase hex (`locator.js:23`; `audio_skellysync/common.py:170` `.hex()`).
- **The offset** is the absolute file position of the first JPEG byte, which is the SimpleBlock payload start (SE §8.1).
- **Scanner prototype:** S `audio_skellysync/common.py:141-215` `scan_mkv`.
  - It reads element headers, the Info and Tracks bodies, and the 4-byte block header.
  - It returns `(track, payload_offset, payload_size, abs_ts_ticks, keyframe, laced)`.
  - It handles unknown-size Clusters, using the Segment end or the file size.

### Conflicts and gaps

1. **The UID text encoding** is undefined (RFF:63 recommends the spec define it). Proposal: 32 lowercase hex characters [I].
2. **The provisional and final offset flags** need fixed bits:
   - `eplib` has `FLAG_OFFSET_LIVE=2`, `FLAG_OFFSET_TAIL=4` and `FLAG_RECOVERED=8`;
   - SE has "offset final".
3. **Embedded sidecar after an ffmpeg remux.** `ffmpeg -map 0 -c copy` copies attachments to before the Clusters and makes a new UID, so the embedded sidecar's UID mismatches. The reader then rejects it and must rebuild by scan (T-S9) [I]. The spec must say what a reader does after a rejection:
   - rebuild by scan with no times available? or
   - pair the old records to the new blocks by CRC and pts = `write_index`, as recovery does (EP §4)? [I]
4. **The audio `.skau`** has no UID while it is live (see §7 gap 6).

### Candidate tests

- **Live-offset writer test (EP/ST):** every live record's offset points at a JPEG whose CRC equals `jpeg_crc32`. Pass: 100 %. Flags: `offset live` (or `tail`) before finalisation, `final` after.
- **Scan = truth:** on golden files with and without audio, the scanned offsets equal the record offsets, and every CRC matches.
- **T-S9:** a golden file remuxed by ffmpeg (UID changed). The reader rejects the sidecar, then re-indexes by scan. Pass: rejection reported and the frames found.
- **The UID in the header equals Info/SegmentUID** in the separate and the embedded copy.

---

## 11. Unfinalised and crashed files

### Decided rules

- **While recording,** the separate sidecar is primary, appended and flushed per frame (SE §7.1; P:158).
- **A separate sidecar exists only before finalisation, or after a crash until recovery** (P:161).
- **Crash recovery** (P row 1.7):
  - on the next start, remux the unfinalised files (about 0.9 s/GB);
  - rebuild the sidecar's offsets and Segment UID against the remuxed file;
  - then rebuild the CSVs and the info JSON (skellycam).
  - MFR O2 proposes changing "rebuild" to "update" for the info JSON.
- **Audio recovery:** the same steps as finalisation, from the killed `.flac` and the surviving `.skau` records. No STREAMINFO patch is needed (FS §5.3).

### Recovery procedure that worked (prototype)

EP §4:192-194, `recover()`:
1. truncate to the valid records;
2. remux;
3. join by pts = `write_index`, with a CRC check;
4. drop packets with no record (0–1 per run);
5. rebuild the offsets by scan.

Result: 38/38 fully paired, 0 CRC mismatches [M].

### Measured facts

**Video kills**
- **Loss per kill** [M] (EP §4 table):

  | Mode | Frames lost per kill |
  |---|---|
  | passthrough | 1–2 |
  | `mjpeg_qsv` depth 4 | 3–5 (4 in every TerminateProcess run) |
  | depth 1 | 1–2 |
  | turbo, 3 workers | 2–3 |

  Loss = frames held in the encoder or pool + 1 held back by the muxer + 0–1 frames "on disk without a record".
- **The record set is always a subset of the muxed set.** No record pointed at a lost frame. Torn 37 B tails were detected by length and CRC in 4/4 runs [M] (EP §4).
- **Earlier kills:** sidecar records = acknowledged frames in 48/48; `recover()` gave the byte-exact prefix in 48/48. MKV+fp never handed out a torn sample in 0/12 prefix cuts [M] (EI:92, 97).
- **A torn tail JPEG decoded silently** in 5/6 PyAV cases [M] (EI:100). So trust only frames that the sidecar records as complete, or check for an EOI (`jpeg_passthrough/FINDINGS.md:627`) [I].
- **A killed MKV** has an unknown-size Segment and no SeekHead. The locator gives `no-seekhead`; the appender refuses [M] (SE §3 table, §4).

**Audio kills (FS §7 `TerminateProcess`, 40 kills: 30 fast, 10 realtime) [M]**
- 0 torn bytes and 0 bad record CRCs.
- 0 frame-CRC mismatches.
- Timing records minus packet records: 0 or 1.
- FLAC frames on disk with no packet record: 0 or 1 (in 4/30; one whole frame of 1,134–1,154 B).
- No partial FLAC frame at the end of the file.
- Recovery gave an exact prefix in 40/40.

**FS §7 "what this means for the spec" [I]:**
- The reader MUST accept one timing record with no packet record, and one complete FLAC frame with no packet record.
- It parses at most one frame after the last packet record.
- It MUST drop a trailing partial record and any record whose CRC fails.
- Power loss and OS crashes were not tested [NV].

**Other**
- PyAV creates the output file at the first mux, so a FLAC writer killed before its first frame leaves no file [M] (AC §2.2).
- Killed native `.flac` files have STREAMINFO total = 0 and still decode [M].
- Unknown-size Clusters are handled by the scanner (`common.py:192`) [C].

### Byte layouts

The live files: see §5 (record) and §7 (`.skau.live` and `.pkt.live` prototypes).

### Conflicts and gaps

1. **Stop or skip at the first bad CRC** (decision 9):
   - `eplib.read_sidecar` stops at the first bad CRC and treats the rest as bad (`eplib.py:70-72`).
   - FS §7 says drop any CRC-failing record.
   - A zero hole after power loss: the overlay study saw MessagePack stop at a 4 KiB zero hole (EI:141).
   - Recommendation: in a live or recovered file, ignore every record from the first failing one onward [I].
2. **A frame on disk without a record.** The prototype drops it (EP §4 step 4). The alternative is to keep it with a "no timing" flag and interpolated times. Decision 10.
3. **The sidecar header is missing.** A crash between `start_encoding()` and the sidecar header write, or before any record, leaves no sidecar or no header. Is the MKV then a "legacy" file? By the ADR-X7FT rule it would be ("no sidecar = legacy"), but it is really a broken new-format file. The spec needs a rule [I].
4. **Can an unfinalised file be played** from the separate sidecar and live offsets without recovery? The player study did not test killed files (NG07; P §2.6:139). Recommendation: the reader MAY play it (live offsets valid for a video-only MKV), but MUST NOT give it to OpenCV (EI:109) [I].
5. **The `mjpeg_qsv` hold-back** is a writer property, not a format rule. Loss bounds can be informative.
6. **Interrupted finalisation** (between scan, fitted write, embed, verify and delete) and interrupted embed (§9 gap 2): a detection and resume rule is needed. The recwriter prototype used a per-stem `.recording.json` with state "recording" / "closed" / "recovered" (S `python_integration/recwriter.py:12, 89-93, 163`) [C]. That is prior art for a crash marker; the spec currently has none [I].

### Candidate tests

- **T-S1 / T-KILL, video** (P:326-330; SE §8.3): kill at each writer point and 3 × TerminateProcess at random times:
  - `before_mux`, `after_mux`, `mid_record` (37 of 64 bytes), `after_record`, `flush` k, `after_container_close`.
  - Pass: every record on disk pairs with a complete frame; a torn record is detected; records ⊆ muxed frames; after recovery the offsets are rebuilt, the UID matches the file, and the file passes the profile check.
- **Audio kill** (FS §7 method: 30 fast + 10 realtime TerminateProcess kills). Pass:
  - every packet record matches the FLAC bytes;
  - recovery accepts the timing-without-packet and frame-without-packet cases;
  - the recovered `.mka` decodes to an exact prefix;
  - at most one frame is parsed after the last packet record.
- **Reader on golden crashed files.** The unfinalised MKV + live sidecar has a torn last record, a CRC-corrupt record and a frame without a record (generated). Pass: the expected record set.
- **Recovery on golden killed files** gives the same output as the reference recovered file (offsets, UID-matching, record set).
- **A crash before the first frame** (MKV with header only, sidecar with header only, or no sidecar). Pass: the reader reports "unfinalised, no frames" without error.
- **Power loss: zero-filled tail** (generated by zeroing the last 4 KiB). Pass: the records stop before the hole; no wrong data.

---

## 12. File, attachment and MIME names

### Decided rules

- The spec fixes the file, attachment and MIME names (ADR-VJ14 item 5; P S6 "Accepted: fixed in the `skellyfileformat` spec").
- **No names are chosen yet.**

### Names found in sources (all proposals or prototypes)

**Video sidecar**
- separate `<stem>.skfr`; attachment `skellycam_frames.skfr`; MIME `application/x-skellycam-frames` (SE §8.2 S6 [I]; the appender default at `append_attachment.py:68`);
- `<stem>.sidecar.bin` (SCOPE §2.2 A7);
- `.frames.bin` (recwriter).

**Audio sidecar**
- attachment `skellycam_audio.skau`, MIME `application/x-skellycam-audio-timing` (`flac_skau.py:173,188`);
- separate `<rec>.audio.skau` (AC §0);
- live files `<rec>.skau.live` and `<rec>.pkt.live` (`terminate_kill.py:89`).

**Media files**
- `<rec>.audio.flac` (live) and `<rec>.audio.mka` (final) (P §2.8; ADR-CA03).
- Camera file pattern today: `{rec}.id-{id}.idx-{idx}.{ext}` [C] (RFF:30, `parse_video_filename.py:13-16`). freemocap parses it, which is a contract for phase 2 (P D26).
- Today's skellysync output: `synced_<name>.mp4` (P §2.9).

### Measured facts

- The locator can match on FileName and/or FileMediaType (locator.js:87).
- FileUID is random (`append_attachment.py:102`).

### Conflicts and gaps

1. **The brand.** Names with "skellycam" are wrong for files that skellysync and the converter write [I].
2. **`x-` MIME types** are unregistered (RFC 6838 discourages `x-`); `vnd.` would need IANA registration [I].
3. **The discovery rule** for the separate sidecar next to its MKV is not decided: "MKV stem + extension"? MFR item 7 requires a discovery rule.
4. **Live audio sidecar names** (one file or two, decision 3).
5. **The camera file name pattern.** Does the spec fix it, or does skellycam? ADR-5PP8 puts "folder layout and file names" in the spec. RFF §5 put them in skellycam's spec before ADR-5PP8.

### Candidate tests

- **Writer:** the attachment FileName and FileMediaType equal the spec values exactly. A separate sidecar has the spec name.
- **Reader:** finds the sidecar by name and MIME. Rejects an attachment with the right name but the wrong MIME (or accepts it: decide).

---

## 13. Files that are not in this format

### Decided rules

- **A recording with no skellyfileformat sidecar is a legacy recording** (ADR-X7FT item 3; P row 1.13).
- **The spec covers only the new format.** skellycam defines how it reads legacy recordings (ADR-X7FT item 6).
- **SPEC §13 tells how to find a file that is not in this format** (README Scope).
- **S10b** (correcting the old audio start, 9–74 ms) is out of scope for this spec (open-work.md).

### Legacy inventory (what old code writes)

From P §2.9:224-232; RFF §1:
- MP4 with H.264 (X264, H264, avc1, PyAV libx264) or `mp4v`; AVI with XviD, DivX or MJPG, all with the burned-in stamp;
- `<stem>.web.mp4`;
- per-camera and multi-frame CSVs;
- `<rec>_info.json`;
- `<rec>.audio.wav` (44.1 kHz int16) + `<rec>.audio_timestamps.json`;
- skellysync `synced_<name>.mp4` (libx264 + AAC);
- freemocap annotated MP4.
- Discovery today uses `VIDEO_EXTENSIONS = {.mp4, .avi, .mov, .mkv, .webm}`.

### Conflicts and gaps

1. **What makes a file conforming needs a definition.** Proposal [I]:
   - (a) an MKV/MKA with an attachment that has the spec FileName and MIME, whose payload starts with the spec magic and a known major; or
   - (b) a separate sidecar with the spec name whose header UID equals the MKV's Info/SegmentUID.
   - The UID is present even in a crashed MKV, because Info is written at the header [M SE §6.2] [I].
2. **Edge cases:**
   - a new-format MKV whose sidecar is lost: by the ADR-X7FT rule it is "legacy", though it is an orphan new file;
   - a native `.audio.flac` with live `.skau` files: in-format, unfinalised;
   - an MKV from another program.
   - Rule needed: a reader MAY rebuild an index by scan for an MJPEG MKV with no sidecar, but then it has no times [I] (SE §7.4: "if both are missing or rejected, rebuild by scanning").
3. **Unknown `major`:** the reader must report "unsupported version", not "legacy".

### Candidate tests

Classification on golden inputs:
- a conforming finalised file;
- a conforming unfinalised file with a separate sidecar;
- an orphan MKV (no sidecar) → "not in this format / index by scan";
- small generated legacy samples (an H.264 MP4, a WAV + JSON) → "not in this format";
- a file with an unknown major → "unsupported".

Pass: each gets its expected class. The legacy reading itself is T-LEGACY in skellycam (P:373), not here.

---

## 14. skellysync camera sidecar header (provisional)

### Decided rules

- **skellysync Design A:** JPEG-in-MKV + the skellyfileformat sidecar + FLAC per camera, built on `skellyfileformat[write]` (SCOPE §7 D-DESIGN; P:16).
- **Reuse the skellycam per-frame format;** do not invent a second one (SCOPE §2.8).
- **skellysync writes the format version from skellyfileformat** (ADR-M4DF item 5).
- **skellysync applies `display_rotation`** as a reader (ADR-CE4D item 4).
- **Provisional** until D-Q, D-FPS, D-HDR and D-DRIFT close (open-work.md; ADR-5PP8 item 11).

### Candidate fields

**Header** (SCOPE §2.8, around line 220): the source file name (basename only, MFR §C), size and a content hash; the source codec, profile, bit depth, range and transfer; `rotation_applied`; `range_converted`; the encoder and knob (for example `mjpeg_qsv gq=94`); the quality definition (D-Q); the nominal rate as a rational; and a sync block.

**Per record:** `source_frame_index` u64 and `source_pts_ns` i64.

**Group sync record** (JSON, one per set; MFR says skellysync-only, SCOPE §2.8): `method`, `reference_camera`; per camera `lag_seconds`, `start_frame`, `confidence`, `fps_rational`, `vfr` flag; `shared_frame_count`, `framerate_policy` (R1/R2), `skellysync_version`, input hashes, sub-frame residual.

**The audio block and the packet table:** see §8.

### Open decisions (SCOPE §7:417-439)

| Decision | Options | What it changes in this format |
|---|---|---|
| **D-Q** (quality basis for re-encodes) | SSIM-Y 0.9961 against the decoded source; fixed q94/gq94; q83 | a header field |
| **D-FPS** | R1 resample to the lowest rate with a source-index map (works with freemocap today); R2 native rates + a slot table (needs P 2.2); R3 both | the per-record source mapping and the time-base kind |
| **D-HDR** | refuse; tone-map to 8-bit and record it; keep originals | source transfer and tone-map fields |
| **D-DRIFT** | out of scope; a second sync point and a rate term | the sync block |

### Conflicts and gaps

1. **Rotation for skellysync.**
   - SCOPE §2.5:172 says "bake the rotation into the pixels … and record `rotation_applied`".
   - ADR-CE4D item 1 forbids pixel rotation for **camera** frames. skellysync re-encodes from decoded sources, so baking a source display matrix is not "camera bytes".
   - MFR item 4 suggests both `display_rotation` and `rotation_applied`.
   - Not decided (decision 15).
2. **No room for the per-record fields** in the 64 B record (§5 conflict 6).
3. **Time base.** The time fields have no host clock; MFR item 6 proposes a "synthetic aligned timeline" kind. How `arrival_ns`, `fitted_ns` and so on are filled for R1 slots is undefined [I].

### Candidate tests

All provisional:
- the skellysync golden file (MJPEG + FLAC 44.1 kHz stereo, embedded sidecar with packet table) reads in Python and JS;
- `rotation_applied` and `display_rotation` behave as specified;
- `source_frame_index` maps each slot to the right source frame (barcode fixture, AS §6 test 1; SCOPE §2.10 "New" items 1–7).

---

## 15 (new). The recording as a whole (ADR-5PP8)

### Decided rules

From ADR-5PP8:
- **Scope:** which files make up one take; the folder layout and names; the shared clock; how a writer records the set; how a reader opens it, also when crashed or incomplete; the manifest (item 1).
- **Each file's sidecar header holds the facts about its recording, and the header is authoritative** (item 2).
- **The recording manifest** (item 3):
  - a derived index of the files and facts of one recording;
  - the writer writes it at finalisation;
  - **a reader MUST be able to open a recording without it**, for example after a crash;
  - **when the manifest and a header disagree, the header wins**;
  - the draft gives its fields and the header fields (gate 1).
- **skellycam's recording info JSON is not the manifest.** It stays a skellycam file (item 4).
- **Legacy recordings stay in skellycam** (item 5).

### Measured and code facts

- **One clock.** Video arrival and MF sample time are QPC (TAO §6.2), and PortAudio time is QPC (0 ± 7 µs) [M] (AC §4.1). So all files of one take compare directly on host ns [I] (MFR A table).
- **Multi-PC rigs** need clock-domain alignment (future) (MFR A).
- **Today's folder layout** [C] (RFF §1):
  - `<rec>/<rec>_info.json`;
  - `<rec>/synchronized_videos/` with the videos, `<rec>.audio.wav` and the audio JSON;
  - `synchronized_videos/timestamps/…` CSVs and stats;
  - `synchronized_videos_README.md`.
  - freemocap resolves `videos` against `sv/` (MFR B; `video_group_helper.py:490-496`).
  - freemocap's planned layout `videos/synchronized/` with `<rec>_recording_info.json` differs (MFR D side note).
- **Today's `recording_start_timestamp`** is taken when `RecordingInfo` is built, not at the first frame. `unix_timestamp_local` = UTC (MFR §F) [C].
- **`time.time_ns()` lags UTC on Windows before Python 3.13.** Phase 1 uses 3.13 (P §2.4) [S].
- **Privacy** (MFR §C):
  - do not store absolute paths (`recording_directory` contains the OS user name);
  - store only `utc_offset_min`, not the zone name;
  - device names can contain a person's name, so never require them;
  - serials link recordings, so hash them.
- **freemocap warns about stale files today** (`video_group_helper.py:406-420`), which motivates `take_uuid` (MFR item 8) [C].

### Candidate header fields that carry the recording facts

MFR MUST 1–7 and SHOULD 8–11 (listed in §5): `camera_label`, `take_uuid`, `group_size`, the take anchor `{take_start_host_ns, take_start_utc_ns, utc_offset_min}`, the stable camera key, the `time_base` kind, nominal rate, `display_rotation`, and the optional `group_position`. They go in every camera sidecar header and the `.skau` header.

### The manifest: candidate shapes (none decided)

- **MFR §E:**
  - a `"skellyfileformat": {"major","minor","prerelease"}` object;
  - every listed header must share the major;
  - headers win;
  - an edit is a format change.
- **MFR O1(b):** `<rec>.sff.json` with version, `take_uuid` and `files[]`. Its stated cost: every producer and crash recovery must write it, and it goes stale on rename, delete or remux.
- **RFF §4(c):** a reusable "file reference" object `{mkv, sidecar, key, segment_uid}` with folder-relative paths.
- **MFR B table drops from any manifest:**
  - the per-camera sidecar path (stale after D16 deletes it);
  - the Segment UID copy ("goes stale after a remux"; the header copy binds).
  - Note: if the manifest is "derived" and rebuilt after recovery, a UID copy is acceptable as a check, but the header wins [I].
- **Prior art for a crash marker:** the recwriter `.recording.json` with `state` = recording / closed / recovered (S `python_integration/recwriter.py:12`).

### Conflicts and gaps

1. **MFR O1 and RFF §6 recommended no spec manifest.** ADR-5PP8 overrode that, so **no source drafts the manifest's name, location, format or field list**. All of it is for gate 1 (decision 2).
2. **Folder layout and file names.** ADR-5PP8 puts them in the spec. No source decides:
   - whether the spec mandates `synchronized_videos/` and the `{rec}.id-{id}.idx-{idx}` pattern (today's freemocap contract), or only SHOULDs them;
   - where skellysync writes.
   - The freemocap contract is phase 2 (P D26) (decision 16).
3. **Membership rule.** Proposal: a recording = the conforming files in one folder (not recursive?) with equal `take_uuid` [I]. A file with another `take_uuid` is stale: warn and ignore. `group_size` lets a reader report a missing camera.
4. **t0 for the player:** `take_start_host_ns`, or the minimum first player time (MFR A table) [I].
5. **Opening a crashed recording:**
   - no manifest;
   - separate sidecars, a `.flac` and live `.skau` files;
   - possibly unrecovered MKVs.
   - The reader must group by the header `take_uuid` and treat each file per §11 [I].
6. **Audio ↔ video mapping:** use the AC §4.3 formula, provisional pending A3 (latency) and A4 (drift).
7. **skellysync recordings:** every camera MKV carries its own audio, there is no `.audio.mka`, and the time base is synthetic. The membership and clock rules need a skellysync variant [I].

### Candidate tests

- **A reader opens the golden 4-camera + `.audio.mka` folder** with and without the manifest. Pass: the same file set, camera labels, rotation and t0.
- **Manifest disagrees with a header** (generated edit). Pass: the header value is used; a warning is reported.
- **A stale file** (another `take_uuid`) in the folder. Pass: ignored, with a warning.
- **A missing camera** (`group_size` 4, 3 files). Pass: "incomplete" reported, and the others open.
- **A crashed folder** (no manifest, separate sidecars, `.flac` + live `.skau`). Pass: it opens per §11, and recovery yields a folder equal to the reference finalised folder (excluding the UIDs changed by the remux).
- **Writer:**
  - every header of one take has the same `take_uuid`, take anchor, `group_size` and clock kind;
  - the manifest is written after the last file is finalised;
  - the manifest is consistent with the headers;
  - no absolute paths in any file (grep).

---

## Appendix A. Golden files: the test vectors needed

Each golden file is committed with its SHA-256 and its generator script (ADR-5PP8 item 9; AGENTS §4). It should be generated with pinned PyAV 19.0.2 and synthetic frames: the prior studies used `testsrc2` (SE §9) and barcode frames (EP §1).

| # | Vector | Why |
|---|---|---|
| G1 | Finalised camera MKV (about 90 frames, small resolution) with embedded sidecar; fitted times valid | §4, §5, §9, §10; T-S10 Python = JS |
| G2 | Same media, pre-embed state: no attachment, separate sidecar | precedence and separate-file binding |
| G3 | Unfinalised (killed) MKV: unknown-size Segment, no SeekHead; live sidecar with live/tail flags, a torn 37 B tail, one frame on disk without a record | §11 reader and recovery |
| G4 | The G3 file after recovery: remuxed, new UID, rebuilt offsets, `recovered` flag | §11 recovery output |
| G5 | G1 remuxed by `ffmpeg -map 0 -c copy` (UID changed, attachment moved before the Clusters) | T-S9 rejection then re-index |
| G6 | Sidecar-only vectors: offsets > 2^32 and near 2^53; INT64_MIN sentinels; all flag bits; fit absent; mixed fit validity | JS u32-halves rule; monotonic player time |
| G7 | Header vectors: higher `minor` with extra header bytes and a larger `record_size`; unknown `major`; `prerelease` > 0; different writer string | §3 |
| G8 | Rotation vectors: `display_rotation` 0/90/180/270 with corner-colour markers (RF §1 method) and the expected upright pixel positions | ADR-CE4D direction |
| G9 | JPEG edge frames: DHT-stripped; trailing bytes after the entropy-coded data (generic-camera style) | the reader must not over-validate |
| G10 | Appender states: no tags; tags; chapters at the header; SeekHead with exactly 1 byte of leftover (width widening); and refusal inputs (existing Attachments, no room, trailing bytes) | §9 |
| G11 | Interrupted-embed states: (a) Attachments appended outside the Segment; (b) Segment size updated, SeekHead not | §9 gap 2 |
| G12 | Large file above 4 GiB with FileData past 4 GiB. **Generate in the test, do not commit** (4.68 GB in SE §3), or skip when there is no room on disk | 64-bit SeekPosition and offsets |
| G13 | `.mka` + embedded `.skau`, mono and stereo 48 kHz, with the packet table and a drift fit (provisional fields) | §6, §7 |
| G14 | Killed `.flac` (STREAMINFO total 0) + `.skau.live` + `.pkt.live`, covering: one timing record without a packet record; one FLAC frame without a packet record; a clean kill | §11 audio rules (FS §7) |
| G15 | skellysync camera MKV: MJPEG + FLAC 44.1 kHz stereo; embedded sidecar with audio packet table; burst fixture (AS §6) | §8, §14 (provisional) |
| G16 | Recording folders: (a) finalised 4 cameras + `.audio.mka` + manifest; (b) the same without the manifest; (c) manifest disagreeing with a header; (d) a stale file from another take; (e) a missing camera; (f) a crashed folder | §15 |
| G17 | Classification set: orphan MJPEG MKV without a sidecar; tiny H.264 MP4; WAV + `audio_timestamps.json` | §13 |

---

## Decisions Dom must still make (before or at gate 1)

1. **Requirement numbering under checker rule 3.**
   - Options: (a) global sequential numbering in document order (later additions to early sections break rule 3); (b) blocks per section (§4 = SFF-100…199, §5 = SFF-200…299, and so on); (c) change the checker rule.
   - **Recommendation: (b).** It stays compatible with the "three digits" and "in order" rules.
   - Also decide where the recording section goes: a new §15, or insert it while the skeleton is still empty. Recommendation: a new §15, to keep the existing heading numbers.
2. **The recording manifest: name, location, format, fields, when written.**
   - **Recommendation:**
     - UTF-8 JSON `<rec>.skellyrec.json` (or similar) in the recording folder;
     - written last at finalisation by an atomic replace, and rewritten by recovery;
     - fields: `skellyfileformat{major, minor, prerelease}`, `writer`, `take_uuid`, `group_size`, `take{start_host_ns, start_utc_ns, utc_offset_min}`, `clock` kind, and `files[]` of `{path (folder-relative), kind (camera|audio), camera_label, camera_key, segment_uid, n_records | total_samples, nominal_rate, display_rotation}`;
     - the header wins; no absolute paths and no device names.
3. **Live audio sidecar files.**
   - Options: two live files (timing, packets) or one file with tagged records.
   - **Recommendation:** two live files, as measured in FS §7, merged into one `.skau` at finalisation.
4. **Normative fields: fixed binary or a JSON block.**
   - **Recommendation:** fixed binary for every normative field (version, sizes, counts, UID, take facts, rotation, rate, clock, table offsets, audio track parameters), plus one optional length-prefixed UTF-8 JSON block for diagnostics only. Readers MUST NOT need it.
5. **`display_rotation` encoding and direction.**
   - Options: clockwise or counter-clockwise; degrees (u16 ∈ {0, 90, 180, 270}) or quarter turns.
   - Evidence: FFmpeg and PyAV use counter-clockwise (RF §2:44); skellycam's own config uses cv2 names, for example `CLOCKWISE_90` (`image_rotation_types.py:6-10`).
   - **Recommendation:** u16 degrees, defined as "the clockwise rotation a reader applies to the stored pixels to show the frame upright", with corner-marker golden files. Either direction works if G8 pins it.
6. **Camera identity fields.**
   - **Recommendation:**
     - `camera_label` (MUST): today's short id, with a length limit;
     - `camera_key` (SHOULD): a 64-bit truncated SHA-256 of a kind-tagged string over vid, pid and serial (or the port path), as MFR O4(ii) recommends;
     - no raw serials in files.
7. **Flag bits and fit validity.**
   - Assign bits for: gap, repeat, encode skip, PTS bumped, fit valid, fit unreliable, offset live, offset tail, offset final, recovered.
   - **Recommendation for monotonic time:** finalisation writes `fitted_ns` for every frame (segment fits) and sets "fit valid" on all frames or none; `fit_unreliable` is informative. Unknown bits are ignored by readers and written as 0.
8. **Record extensibility.**
   - Options: (a) the record is fixed at 64 B for the whole major; (b) `record_size` ≥ 64 lets a minor append fields.
   - **Recommendation: (b),** with the record CRC always in the last 4 bytes, covering all the bytes before it.
9. **CRC failure in live and recovered files.**
   - Options: stop at the first failure, or skip and continue.
   - **Recommendation:** stop at the first failure (or the first torn tail), and ignore the rest.
10. **A frame on disk without a record, at recovery.**
    - Options: drop it (prototype), or keep it with a "no timing" flag.
    - **Recommendation:** drop it. It has no capture time, and EP measured this as "never a wrong pairing".
11. **Integrity of finalised sidecars.**
    - Options: (a) none (trust finalisation); (b) a CRC-32 or SHA-256 of the record area in the header, written at finalisation; (c) a header CRC only.
    - **Recommendation:** (b) plus (c). One hash of a few MB is cheap and lets readers skip per-record CRCs (ADR-69YS item 6) while still detecting damage.
12. **Interrupted embed and finalisation recovery.**
    - **Recommendation:**
      - if bytes follow the Segment end, or the Segment ends with an Attachments element that the SeekHead does not reference, truncate them and re-embed from the separate sidecar (which still exists by ADR-77Z3);
      - add a finalisation-state marker, for example a header flag "finalised" set as the last step before the embed.
13. **Precedence of embedded against separate sidecar.**
    - **Recommendation:** embedded with a matching UID wins; else separate with a matching UID; else rebuild by scan. This resolves the conflict between SE §7.4 and MFR item 7.
14. **Clock ids.**
    - **Recommendation:** u8 or u16 enum (1 = Windows QPC, 2 = Linux `CLOCK_MONOTONIC`, 3 = macOS `mach_absolute_time`/`CLOCK_UPTIME_RAW`, 0x80 = synthetic aligned timeline for skellysync), plus the frequency.
    - Values 2 and 3 are provisional until T-S7 and the Linux/macOS tests.
15. **skellysync rotation and per-record source fields.**
    - Rotation options: bake the source display matrix and record `rotation_applied`, or keep the pixels and set `display_rotation`.
    - **Recommendation:** keep `display_rotation` only, for one rule across producers.
    - Per-record fields: put `source_frame_index` in `source_frame_number` (u32 is enough at 60 fps for about 2.3 years), and put `source_pts_ns` in `sample_time_ns`, with the field meanings defined per `time_base` kind. Keep this provisional under D-FPS.
16. **Folder layout and file-name rules in the spec.**
    - **Recommendation:**
      - MUST: a recording = conforming files in one folder with an equal `take_uuid`; the separate sidecar is named `<media stem>.<ext>`;
      - SHOULD: the `{rec}.id-{label}.idx-{n}.mkv` and `<rec>.audio.mka` names and the `synchronized_videos/` folder (today's freemocap contract);
      - readers MUST NOT depend on names for anything else.
17. **Attachment and MIME names (S6).**
    - **Recommendation:** brand-neutral names, for example FileName `video_timing.skfr` / `audio_timing.skau`, MIME `application/x-skellyfileformat-video-timing` / `application/x-skellyfileformat-audio-timing`, extensions `.skfr` / `.skau`, and live files `.skfr` / `.skau.live` / `.pkt.live`. Readers match FileName and MIME.
18. **The meaning of `legacy_ns`, and of the time fields per producer.**
    - **Recommendation:** `legacy_ns` is "writer-defined compatibility stamp; INT64_MIN if none". Define `arrival_ns`, `sample_time_ns` and `fitted_ns` per `time_base` kind and producer (live capture, converter, skellysync).
19. **The definitions of nominal rate and fitted time.**
    - **Recommendation:**
      - nominal rate = the rational used for the container pts (the requested or configured rate), with the delivered rate derivable from the times;
      - fitted time = the writer's lattice estimate on the host clock, not capture time; latency is not included.
20. **Mandatory embed and its fallback.**
    - **Recommendation:** embed is a writer MUST when the appender's preconditions hold. Otherwise the separate sidecar is the final form, with a header flag.
21. **Version values written by today's prerelease builds.**
    - **Recommendation:** `major`=2, `minor`=0, `prerelease`=N, until v2.0.0.
22. **The UID text form in the manifest and in diagnostics.**
    - **Recommendation:** 32 lowercase hex characters.

**Notes on scope.** The writer and implementation tests from T-MKV and T-S6 (`mjpeg_qsv` pts unchanged at 1/fps; delay = `async_depth` − 1; `encode(None)` terminal) are skellyfileformat[write] or skellycam tests, not format conformance tests. T-S3, T-S4 and T-S5 are performance and transport tests that belong to skellycam (P D22).
