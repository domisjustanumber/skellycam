# skellyfileformat spec v0: third sub-agent review (2026-11-12)

Provenance: three read-only sub-agent reviews of `skellyfileformat` `spec/SPEC.md` + `spec/conformance.md` at commit bd62b60 (local, revision 2): (1) layouts and internal consistency (fresh), (2) fidelity to Q1–Q26, D1–D6, E1–E7, the active ADRs and the two desk tests, with a fix check of `spec_v0_rereview_20261112.md`, (3) outsider implementability and testability (fresh). Merged by the main session. Not yet checked by the main session against the files, except where noted.

**Fix check (reviewer 2):** every E1–E7 answer and nearly every item of the second review is fixed. Byte layouts, flag tables, ID blocks, references and test arithmetic are consistent (reviewers 1 and 3 recomputed the `camera_key`, CRC check value, 501 ms tie and Seek-entry sizes).

## Blockers (crash and reader rules)

1. **Re-embed of a final separate sidecar** (reviewers 1, 2, 3). §9.7 row 4 ("finalised separate sidecar, matching media, no attachment → steps 5 to 7") also matches a finished `separate_final` file, so a recovery re-embeds it; after a step-6 cut the appender accepts, giving an embedded sidecar with `separate_final` set and the separate one deleted. Row 5 ("step 5 again") does the same. Fix: row 4 only when `separate_final` is clear; new row "`separate_final`, no attachment → `finalised`, step 7 only (audio)"; row 5 → rename the temporary copy if its CRCs pass, else redo step 5.
2. **Missing crash rows** (1, 2, 3): a kill after the embed but before step 7 (embedded-only `.mka` plus `.flac` and `.skat.live`); a kill between the two deletes of step 7 (orphan `.skat.live` or `.flac`). State the delete order and add rows. SFT-350/361 also require "separate sidecar deleted", which fails for every `separate_final` outcome.
3. **SFF-363 cut order** (3): a crash after the truncate but before the size restore, or after the size restore but before the SeekHead rewrite, leaves states that are not in SFF-362. Fix: (1) rewrite the SeekHead span without the Attachments entry, flush; (2) restore the Segment size, flush; (3) truncate.
4. **Torn SeekHead cannot be recovered as written** (3): if the span is torn, its end is unknown. Fix: SFF-352 step 3 is one write call (a process kill does not tear a single write already in the kernel; the spec covers process kills only), and keep a resync rule (find Info by its `SegmentUID`).
5. **Reader result shape** (3): warnings have no codes and there is no canonical result, so "Python and JS give the same result" and "golden expected results" cannot be compared. Add a canonical reader-result JSON with per-file state and reason, per-take state, warning codes (`stale_file`, `manifest_mismatch`, `duplicate_label`, `take_fact_mismatch`, `multiple_manifests`, `incomplete_take`) and record fields.
6. **Missing reason codes and states** (1, 3): no code for a bad `display_rotation`, a zero rate, a `segment_uid` mismatch, a refused prerelease, the JS 2^53 error, a truncated sidecar; `not_in_format` is not in the precedence order; "unsupported version" vs `unsupported_version` in SFF-051, SFF-552, SFT-056.
7. **Camera file vs audio file is not defined operationally** (3): `.mkv` and `.mka` share the magic. Fix: "a Matroska file with a `V_MJPEG` track is a camera file; one with only an `A_FLAC` track is an audio file; the scan uses the `V_MJPEG` track".
8. **Latency sign in SFF-261 (provisional)** (1): with `audio_latency_ns` defined as microphone → ADC, sound at time T is at sample n0 + (T + L − t0) × f / 10^9, not − L; the two formulas are not inverses. The research digest (AC §4.3) has the same minus sign with a different meaning of t0. Pick one definition and make the formula agree.

## Majors

- SFF-208 garbled: the `.flac` binds to its live sidecar by stem (SFF-550); the `.mka` pairs with the take by `take_uuid`. When a take has a finalised `.mka`, the `.flac` gets a defined state (proposal: `superseded`). (1, 3)
- SFF-503 MAY vs §9.7 row 2 MUST: make noting `<media>.tmp` a MUST with an exact condition. (1, 2)
- Step 6 cites SFF-363, which ends by embedding again; say "without the new embed". Verify failure from a changed frame CRC should go to recovery, not `separate_final` (it hides damaged media). (1, 3)
- Step-2 failure during a recovery loops back to "do a recovery". (2)
- Drift record size unstated (say `record_size`); `json_size` must be 0 when `json_offset` = 0; readers must not assume tables are contiguous. (1, 3)
- SFT-057 places the JSON block at 268, against SFF-004 (must start at a multiple of 8). (1)
- SFT-660 expects `damaged`, but SFF-158 makes the `body_crc32` check optional. (1, 3)
- SFT-550 expects a state for the MP4 and WAV, which are not candidate files (SFF-504); a folder whose only files are `unsupported_version` has no recording state. (2, 3)
- A stale manifest hides newer takes: a live or crashed take 2 next to take 1's manifest is ignored, against SFF-655. Fix: only files the manifest lists can make another stale; a `live` or `needs_recovery` file is never stale. Or one take per folder. (3)
- Multi-take folders: define the result as a list of takes; each manifest governs only its own `take_uuid`. (3)
- A `needs_recovery` file is not "in this format", so its take is reported `incomplete`. Count it in its take. (3)
- SFF-104 arithmetic overflows u64 for large `nominal_rate_den`: bound num and den (e.g. ≤ 2^20) and refuse larger as `bad_rate`. (3)
- `camera_key` (and other u64 ids) cannot be exact in JS: give them as decimal strings. (1, 3)
- The Segment UID read-back needs `avio_flush` after the header; "flush to the file" vs "flush to the disk" undefined. (3)
- Windows: a player holding the live `.mkv` open without `FILE_SHARE_DELETE` blocks the recovery rename. (3)
- `adc_ns` unusable streams (MME alternates 0 / 23.2 ms): write INT64_MIN for every record, not only the zero ones. (2)
- `separate_final` meaning should cover both causes (appender refused, embed did not verify). (1, 2)
- SFF-204 compares with `total_samples` before step 3 writes it: compare with the sum of `n_samples`. (1)

## Minors

- README Scope `.skat` bullet still says only "as an attachment". (2)
- ADR-FGK2 item 8 ("no columnar or compact section") and ADR-5K7G item 3 ("the player draws the frame label from the sidecar") are not stated; needed before those entries can be absorbed. Q25's "3 reads" dropped from SFF-357. (2)
- SFF-301 has no open-work item; SFT-300 (provisional) is the only test of final SFF-300/302; "A4" label not in open-work. (2)
- `table_offsets_final` describes a case that never happens; `fit_unreliable` name reused for drift records; SFT-503 names "§9.7 row 2"; G7 list misses three inputs the tests use. (1)
- SFT-360 does not recompute `header_crc32`; SFT-170 names the attachment but not its media type; SFT-661 lacks a `take_start_utc_ns` variant; SFT-402 does not use G12; SFF-405 never exercised (G3 has an unknown-size Segment, not unknown-size Clusters). (2, 3)
- Matroska details: smallest-width rule must skip the reserved all-ones VINT; copy old Seek entries byte for byte; the RFC 8794 end rule for unknown-size Clusters; whether reading a Cluster header counts as "inside" (SFF-359). (3)
- Appendix A's "patch a `SegmentUID`" grows Info and shifts every later byte; overwrite in place on a non-bitexact mux instead. The bitexact claim itself is unverified (from memory). (2, 3)
- FFmpeg may add a VORBIS_COMMENT block to FLAC CodecPrivate for non-default channel layouts (from memory): limit to mono/stereo or set CodecPrivate in the writer. (3)
- Tests stricter than their requirements (SFT-165 1 ms, SFT-204 100 ms); untested halves listed by reviewer 3 B8; criteria not concrete (SFT-201 "flushed", SFT-357 I/O tracing, SFT-255 tolerance). (3)

## Decisions for Dom (proposed)

- **F1.** Embed verify failure: when the attachment's SHA is wrong, cut it and set `separate_final`; when a frame CRC changed, go to recovery (media damage)?
- **F2.** Stale files: only files a manifest lists can make another file stale, and a `live` or `needs_recovery` file is never stale (or: one take per folder for writers)?
- **F3.** Latency (provisional): define `audio_latency_ns` as microphone → ADC and use + L in SFF-261?
- **F4.** Add a canonical reader-result JSON (states, reasons, warning codes, records) as a spec section, so Python/JS and golden results can be compared?
- **F5.** A `.flac` whose take has a finalised `.mka` gets a new state `superseded`?
- **F6.** Bound the nominal rate fields (num and den ≤ 2^20) to keep SFF-104 inside 64-bit arithmetic?
