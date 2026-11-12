# skellyfileformat spec draft: Dom's answers to the open choices (2026-11-12)

Provenance: grilling rounds with Dom on 2026-11-12, working from the 22 open choices in `spec_inputs_digest.md` and the open questions in `research/HANDOFF_20261112_skellyfileformat_spec.md` §5. Every item below was accepted by Dom. `SPEC.md` and `conformance.md` in `skellyfileformat` are drafted from this list (step 5, then gate 1).

## Structure
- **Q1** Requirement ids are numbered in blocks per section. The whole-recording section is a new **§15**; existing heading numbers stay. *Drafting note:* the example blocks of 100 (§15 = SFF-1200) break the three-digit id rule, so the draft uses **blocks of 50**: §2 = SFF-001…049, §N = (N − 2) × 50 onward (§5 = SFF-150, §15 = SFF-650). Flagged for gate 1.

## Header and record
- **Q2** Header fields: MFR items 1–11. **`take_uuid`, `group_size` and the take anchor `{take_start_host_ns, take_start_utc_ns, utc_offset_min}` are MUST.** `camera_key` is SHOULD. `group_position` is optional.
- **Q3** Every normative field is fixed binary. One optional length-prefixed UTF-8 JSON block is for diagnostics only; readers MUST NOT need it.
- **Q4** `display_rotation`: u16 degrees ∈ {0, 90, 180, 270} = the **clockwise** rotation a reader applies to the stored pixels to show the frame upright. Any other value does not conform. Pinned by golden G8 (corner markers).
- **Q5** `camera_label` MUST (short id, with a length limit). `camera_key` SHOULD: a 64-bit truncated SHA-256 of a kind-tagged string over vid, pid and serial (or the port path). No raw serials in files; they stay only in skellycam's local cache. A writer refuses duplicate `camera_label`s within one take; a longer label can come in a later minor.
- **Q6** Record flags: bit 0 gap, 1 repeat, 2 encode skip (on the record after the failed frame), 4 fit valid, 5 fit unreliable (informative), bits 6–7 offset state (0 live, 1 live found by tail search, 2 final, 3 reserved), 8 recovered. **PTS bumped is dropped** (pts = `write_index` always increases). Bit 3 is unused. Finalisation writes `fitted_ns` for every frame (segment fits) and sets fit valid on all frames or none. Readers ignore unknown bits; writers write them as 0.
- **Q7** The header carries `record_size` (≥ 64, a multiple of 8). A minor may add fields before the CRC. The record CRC is always the last 4 bytes, covering every byte before it. Readers step through the file by `record_size`.
- **Q10** Finalised sidecars carry a CRC-32 of the record area and a CRC-32 of the header. A reader that checks the area CRC may skip the per-record CRCs.

## Live files, crashes, recovery
- **Q8** On a CRC failure or a torn tail, a reader stops at the first one and ignores everything after it.
- **Q9** At recovery, a frame on disk without a record is dropped.
- **Q11** **One** live audio sidecar, `<rec>.skat.live`. Timing and packet records are the same size, carry a type field, and keep the CRC in the last 4 bytes. Write order per block: timing record → FLAC frame → packet record. Finalisation produces one `.skat`. The 40-kill test (`flac_skau/terminate_kill.py`) is rerun against the one-file writer before gate 2.
- **Q24** Interrupted embed: bytes past the Segment end, or an Attachments element at the end of the Segment that the SeekHead does not reference, means "not embedded yet". A reader uses the separate sidecar. Recovery truncates back to the old Segment end, restores the Segment size and embeds again. The sidecar header gets a **finalised** flag, set as the last change to the separate sidecar before the embed; `finalised` = 0 means finalisation never finished (§11 applies).

## Embedding and finalisation
- **Q12** Precedence: the embedded sidecar if its UID matches the file; else a separate sidecar with a matching UID; else rebuild by scan.
- **Q13** Embedding is a writer MUST when the appender's preconditions hold. Otherwise the separate sidecar is the final form, a header flag says so, and the writer does not delete it.
- **Q20** Timing stays in sidecars (ADR-69YS). It is not carried inside JPEG/FLAC frames: FLAC frames have no space for our data, and the index is needed anyway.
- **Q25** Finalisation order per file: (1) remux if needed; (2) scan the final MKV, rebuild offsets, check each frame CRC; (3) write `fitted_ns` + flags (offset state final), `n_records`, the final UID; recompute the record CRCs, then the area CRC and header CRC; set `finalised` last; (4) embed; (5) verify = embedded FileData SHA-256 equals the separate sidecar's, the locator finds it in 3 reads, and the first and last frame CRCs match; (6) delete the separate sidecar. The manifest is written after every file finishes step 6. Audio follows the same order, with the §7 packet-table steps.

## Values and names
- **Q14** Clock id: u16 enum, 1 = Windows QPC, 2 = Linux `CLOCK_MONOTONIC`, 3 = macOS `mach_absolute_time`/`CLOCK_UPTIME_RAW`, 0x80 = synthetic aligned timeline (skellysync), plus the frequency. Values 2 and 3 are provisional until T-S7 and the Linux/macOS tests.
- **Q15** Prerelease builds write `major` = 2, `minor` = 0, `prerelease` = N until v2.0.0; after that, `prerelease` = 0.
- **Q16** UID text form: 32 lowercase hex characters, no dashes.
- **Q17** Extensions and magics: **`.skvt` / `SKVT`** (video timing) and **`.skat` / `SKAT`** (audio timing). Attachment FileNames `video_timing.skvt` and `audio_timing.skat`. MIME types `application/x-skellyfileformat-video-timing` and `application/x-skellyfileformat-audio-timing`. Live audio file `<rec>.skat.live`. Readers match on both FileName and MIME type. (Not checked for clashes with existing registered extensions.)
- **Q18** `legacy_ns` = a compatibility stamp the writer defines, or INT64_MIN if none. `arrival_ns`, `sample_time_ns` and `fitted_ns` are defined per `time_base` kind and per producer. Nominal rate = the rational used for the container pts (the requested rate). Fitted time = the writer's lattice estimate on the host clock; it is not capture time and does not include latency.

## The recording as a whole
- **Q21** Manifest `<rec>.skellyrec.json` in the recording folder: UTF-8 JSON, with **64-bit integers as decimal strings**. Written last by temp file + rename; crash recovery rewrites it. Fields: `skellyfileformat{major, minor, prerelease}`, `writer`, `take_uuid`, `group_size`, `take{start_host_ns, start_utc_ns, utc_offset_min}`, `clock{id, freq}`, `files[]` of `{path (folder-relative), kind (camera|audio), camera_label, camera_key, segment_uid, n_records | total_samples, nominal_rate{num, den}, display_rotation}`. No absolute paths, device names or raw serials. Headers win. skellysync writes one too.
- **Q22** A recording is the conforming files directly inside one folder (subfolders are not searched) that share a `take_uuid`. A file with another `take_uuid` is ignored, with a warning. Fewer camera files than `group_size` means the reader reports "incomplete" and opens the rest. A separate sidecar is named `<media stem>.skvt` / `.skat`. The manifest name is fixed (Q21). Everything else (media file names, `synchronized_videos/`, `{rec}.id-{label}.idx-{n}`) belongs to skellycam's spec. Readers take nothing from file names apart from finding the sidecar.
- **Q23** Player t0 = `take_start_host_ns`. The player shows nothing for a camera before that camera's first frame.
- **Q26** skellysync: `display_rotation` only, no `rotation_applied`. `source_frame_index` → `source_frame_number` (u32), `source_pts_ns` → `sample_time_ns`, defined for the synthetic `time_base` kind. Provisional until D-FPS; wider fields go in via `record_size` (Q7).

## skellycam's own spec (not skellyfileformat)
- **Q19** skellycam writes `<rec>_info.json` at record start and updates it at finalisation; adds `info_version`; stops writing the absolute `recording_directory`.

## Drafting detail (settled in the draft; Dom can object at gate 1)
- Before finalisation, a live `.skat` binds to its `.flac` by `take_uuid` and name (a `.flac` has no Segment UID).
- A header flag says whether packet offsets point into the `.flac` (live) or the `.mka` (final).
- The `.skat` header carries the packet table's offset and count. Zero-size packets are skipped.
- Provisional: the drift-fit segment table and `audio_latency_ns` (open-work A3/A4), and the audio → video mapping formula.
