# skellyfileformat spec draft v1: sub-agent review (2026-11-13)

Provenance: one read-only sub-agent review of `skellyfileformat` `spec/SPEC.md` + `spec/conformance.md` at commit f420238 (draft v1, the MCAP profile), against the active decision entries, the MCAP spec and registry, the Foxglove CompressedImage/CompressedAudio/Log .proto files and RFC 7845 (fetched). It did not fetch RFC 8785 or RFC 4648, did not read the mcap_single_writer or lichtblick_check findings, and checked the IDs by grep only. The main session checked B1–B3, S2 and S7 against the spec and entry text: all confirmed. Dom's answers are at the end.

## Blockers

- **B1. Fit segments keyed by `sequence`** (SFF-267, SFF-268, SFF-271, `segments` key). A camera restart resets the frame number, so one sequence value can be in two segments (FF01 item 2 starts a segment at a restart). After a wrap, "in order of `seq_first`" no longer matches file order (G10). Fix: key segments by position, contiguous, in position order.
- **B2. "Refuses" has no file state** (SFF-009, SFF-184, SFF-186, SFF-679, SFT-006). SFT-006 uses `not_in_format`, which contradicts SFF-555/556. `bad_label`, `bad_schema`, `missing_metadata` and `crc_mismatch` have no triggering rule. Not stated whether a refused file joins its take or counts for `group_size`.
- **B3. "In this format" defined two ways** (SFF-555 vs SFF-556). A folder whose only files have an unknown `major` falls to `legacy`, which SFF-060 forbids. No `folder_state` for such a folder; no placement of `unsupported_version` files in the result.
- **B4. Reader result under-defined** (SFF-010, SFF-678): integer string-vs-number decided per field or per value; ±2^53 boundary (JS safe range is ±(2^53 − 1)); time base of `records`; absent vs null members per file kind; order of `other_files`; file-level `warnings` sort; tie in SFF-192 ordering (two cameras with one label); take-level vs file-level warnings; `packet_index` meaning; `torn_bytes` of a `damaged` file.

## Should fix

- **S1.** No rule places Schema and Channel records; a torn first Chunk loses the label, `frames_per_chunk`, rotation and `opus_head`. Fix: write them outside Chunks, before the first Chunk.
- **S2.** SFF-375 cuts after the last good Chunk; ADR-S4FG item 7 says "cuts off any torn bytes after the last complete record". "With its complete Message Index records" reads two ways. No rule for zero complete Chunks. A file re-chunked by `mcap recover` breaks SFF-120 silently.
- **S3.** SFT-368 "same file" after an interrupted repair cannot hold: `cut_bytes` differs on the second run.
- **S4.** A zero-filled tail parses as complete opcode-0 records. Fix: opcode 0x00 or a length past the end ends the read.
- **S5.** Chunk CRC checks on finished files undefined; `crc_mismatch` has no rule. A computed CRC-32 can be 0, which MCAP reads as "not validated".
- **S6.** HD8Z item 3 calls `sample_rate` the OpusHead input sample rate (can be 44100); spec fixes 48000. No rule applies the output gain (RFC 7845: players SHOULD), and SFF-217 does not check it.
- **S7.** ADR-QDZ7 item 2 bases audio `log_time` on the first decoded sample; ADR-752H item 2 and SFF-212 say arrival time. The desk tests used `log_time` = `timestamp`.
- **S8.** ADR-752H item 4 (conversion writer writes an old timestamp as arrival time) is not in the spec.
- **S9.** ADR-68Z6 item 3 (no EXIF orientation or other rotation) is not in the spec; no reader rule ignores EXIF orientation; SFF-185 has no writer test.
- **S10.** ADR-WD9A and ADR-10JC have no test; MCAP CLI version not pinned in "the MCAP checks".
- **S11.** ADR-VJ14 item 5 (spec fixes names) contradicts ADR-DK8S item 12; VJ14 items 2–3 and ADR-5K7G item 3 describe the sidecar; X1G6 items 1, 4, 5 are skellycam rules but are on the absorb list.
- **S12.** Gate-1 name confirmations and other new v1 names (`group_position`, `clock_freq_hz`, `utc_offset_min`, `result_version`, the state/reason/warning vocabularies) have no decision entry.
- **S13.** No writer rule that segments cover every frame; `(s − seq_first) × period_ps` passes 2^53 after about 2.5 h at 30 fps.
- **S14.** A lost audio file is not detectable; no rule for more camera files than `group_size`.
- **S15.** SFF-191 does not say when the warning `encode_skip` is given; SFF-190 gives no `publish_time` or `sequence` for the Log Message.
- **S16.** SFF-063 prerelease refusal has no result vocabulary, yet results must be byte-equal.
- **S17.** SFF-116 does not require the imports (`google/protobuf/timestamp.proto`) in the FileDescriptorSet (MCAP registry: `protoc --include_imports`).
- **S18.** SFF-215 has no rule for k < 4.
- **S19.** SFT-211 not provisional but checks provisional SFF-216; SFT-006 cites SFF-010 with no JSON vector in G7; SFT-059 "magic version byte" vector not in G6; SFT-007 near-2^53 file not in Appendix A; SFT-261 checks screen behaviour the result cannot show.

## Nits

SFF-011 includes `take_start_utc_ns` in "host clock"; relative times can be negative (SFF-670, SFF-012); `<serial>` encoding differs across OSes (SFF-183); no reader rule for an unknown `clock_id`, a malformed `take_uuid` or `opus_head`, a duplicate `freemocap.format`, or two audio files in a take; use of a complete `freemocap.timing` in an unfinished file; skellysync files always give `missing_fit` (SFF-306); SFT-366 names only `TerminateProcess`.

## Checked, nothing serious

MCAP magic, CRC "0 = not available", `publish_time`, Summary contents, no Attachments in chunks; Foxglove field numbers and Log `WARNING` = 3; RFC 7845 references; RFC 4648 §4; versioning against ADR-7K3C; topics and channels against ADR-DK8S; chunk rules against ADR-S4FG items 1–4; provisional markers.

## Dom's answers (2026-11-13)

- Keep skellyfileformat a separate repo.
- Gate-1 names confirmed: `freemocap.repair`, audio `label`, `audio_latency_ns` in the audio channel metadata, RFC 8785.
- B1: key fit segments by position.
- S2: the repair cuts after the last good Chunk (supersede ADR-S4FG item 7).
- S7: audio `log_time` is the arrival time (supersede ADR-QDZ7 item 2's parenthesis).
- S6: `sample_rate` is the 48 kHz decode rate, not the OpusHead input rate; writers write output gain 0.
