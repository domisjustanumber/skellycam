# skellyfileformat spec v0: merged sub-agent review (2026-11-12)

Provenance: three read-only sub-agent reviews of `skellyfileformat` `spec/SPEC.md` + `spec/conformance.md` at commit 2cc2fb0 (local): (1) byte layouts and internal consistency, (2) fidelity to `spec_draft_decisions_20261112.md` and the active ADRs, (3) implementability and testability by an outsider (read only the spec, README and conformance list). Merged and checked by the main session. Checks made by the main session: the killed-FFmpeg-MKV shape (`results/sidecar_embedding/FINDINGS.md` table rows "Killed at frame 61 → no SeekHead" and "Crashed file … no-seekhead"); the SeekHead CRC handling (`scripts/sidecar_embedding/append_attachment.py:91-93` recomputes it); frames on disk without a record (`results/encoder_pairing/FINDINGS.md:185`, "0–1").

Arithmetic of every byte table was checked by reviewer 1: no gaps, overlaps or misaligned fields; minimum header sizes 272/256 consistent; WebCodecs description correct; all SFF/SFT/G references resolve.

## Blockers (no decision needed; the fix is clear)

1. **SFF-402 live offset wording is wrong** (all three reviewers). The text says record k is written "after the container has written frame k + 1". The measured rule is: after `mux(k+1)` returns, the file ends at frame k (frame k+1 is held back), so offset = file size − size(k). Also define the end-of-file search (`offset_state` 1).
2. **SFF-105 is wrong for live files.** FFmpeg writes the SeekHead only at close, so a killed file has no SeekHead (measured). SFF-105 must apply after the container closes, before the embed. Add: a reader of a live file finds `Info`/`SegmentUID` by walking the top-level elements from the Segment data start. Add: `SegmentUID` is present, random and not all zero.
3. **Crashes during finalisation are not covered.** Step 3 doesn't say whether it writes in place or to a new file; the step-1 remux has no file naming; the audio `.mka`/`.skat` have no temporary names. A crash mid-step-3 leaves a half-final sidecar that recovery would treat as live; a crash after the remux replaces the file loses the timing (UID mismatch). Fix: write new file → flush → rename for the sidecar and the remux output, keep the original until the new sidecar is in place, and add a crash-state table to §9 (step × files present × reader result × recovery action).
4. **Audio write order cannot be followed** (SFF-257, also reviewer 2 C8). FLAC frames and callback blocks need not line up. Fix: "a packet record follows its frame before the next frame is written; a timing record precedes every frame that holds any of its samples." Also: CodecPrivate = `fLaC` + STREAMINFO only (no SEEKTABLE, whose offsets are wrong in the `.mka`); say which STREAMINFO (after close); give the audio block timestamp rule.

## Majors (fix in the spec; no decision needed)

- Audio record CRC range is written as "bytes 0 to 43 (version 2.0)": write `record_size` − 5, and say new audio fields go after byte 43 (minor-version growth, ADR-FGK2).
- Unnamed header bytes 264–267 (video) and 248–251 (audio): add reserved rows; add `header_crc32` rows; rule for the JSON block (`json_offset` ≥ end of fixed fields, ends before `header_crc32`, all other bytes 0).
- `separate_final` is set after `finalised` (SFF-354 vs Q24 / ADR-3KH3 item 6 "last change"): in SFF-350, add the refusal branch (set `separate_final`, skip steps 5–6), and call it the one allowed change after `finalised`.
- `gap` vs `repeat` overlap (SFF-170): `gap` when ≠ prev + 1 and ≠ prev.
- Container timestamp rounding (SFF-104): a tie exists at 30000/1001, k = 15 (500.5 ms). Fix TimestampScale at 1 ms, round half up with integer arithmetic, timestamps strictly increasing.
- Appender (SFF-352/353): recompute the SeekHead CRC; the new Seek entry uses an 8-byte SeekPosition (21 bytes), and "room" = the SeekHead + Void span; refuse when the new Segment size does not fit the old width; apply SFF-105/106 to the `.mka` too.
- Reader validation is missing: header sizes below the minimum or not multiples of 8, tables or JSON outside the sidecar, `header_size + n_records × record_size` larger than the file, wrong magic for the file kind (SKAT in a camera MKV), a bad embedded sidecar falling back to the separate one. In a finalised sidecar with a bad `body_crc32`, stop at the first bad record CRC (Q8 applies to all sidecars).
- Zero frames / zero samples: verify (first/last frame CRC) and fitting are undefined.
- Reader results are used by the tests but never defined ("in format, finalised", "live, no frames", "incomplete", "unsupported version"); `group_position` is defined but unused, while SFT-502 checks "order". Add a result model and a camera-order rule.
- skellysync `sample_time_ns` = source presentation time is not on clock 0x80, yet `clock_id` is "the clock of all times in this sidecar", and §1 defines sample time "on the host clock".
- "Fitted time … does not include the camera latency" reads as the opposite of the measurement (the fit lags capture time by an unmeasured latency). Reword: "not corrected for latency".
- Audio recovery says "set `recovered`", but audio records have no such bit: it is the header flag.
- `fit_unreliable` (video) has no rule; `first_sample` has two meanings (packet vs drift segment); `table_offsets_final` only applies when a table exists; §1 says §13 tells how to "find" legacy files (it classifies them).
- Golden-file mismatches: SFT-202 uses "the recovered `.mka` of G14" (not in Appendix A); SFT-255 needs G13 with "a known drift with one step"; SFT-358 needs "G5 next to G2's separate sidecar".
- Test sharpening:
  - SFT-451 "equal to G4" is too strict for another writer (offsets and fits differ). Compare the record fields; check offsets against a scan of the writer's own output.
  - SFT-350 needs the crash-state table (blocker 3), with kills after each write or rename.
  - SFT-157 needs a fixed vid/pid/serial and the expected u64 (or SFF-162 stays a free choice).
  - SFT-102/601: give the expected value (90) and the corner colours.
  - SFT-202: use a vector with a wrong non-zero STREAMINFO total.
  - SFT-453: state the method (signal, window, seed, count).
  - SFT-357: "3 reads" → "at most N byte ranges, none inside a Cluster".
  - Untested halves: writer output is only checked through golden files for the codec requirements; no bad-magic input; no "first child not a SeekHead" input; reserved-byte non-zero not tested; reader side of the SFF-454 audio states untested.
  - Wording that cannot be tested: SFF-158 SHOULD, SFF-175 "stalled or stepped", SFF-260 "about 3 ms", SFF-651 "same moment", SFF-653 "device name".

## Decisions for Dom

- **D1.** ADR-5PP8 item 1 says the spec covers "the folder layout and the file names"; Q22 and ADR-WD1R item 5 say it fixes only the sidecar and manifest names. A new entry must supersede 5PP8 in full on this point.
- **D2.** SFF-656: with no manifest and two takes in one folder, the draft reports each take. Q22 says a file of another take is ignored with a warning (which needs a manifest to know which take is current).
- **D3.** Manifest member `clock.freq_hz` (draft) vs `clock.freq` (Q21).
- **D4.** SFF-175 makes fitted times optional ("a writer that writes fitted times"). Q6 / ADR-0YV1 say finalisation writes them for every frame. Make them a MUST for capture writers, with converters and skellysync allowed to omit them?
- **D5.** Provisional tags: SFF-602 (skellysync rotation), SFF-301 (skellysync audio window by nominal rate), `adc_ns`/`current_ns` meaning on Linux/macOS.
- **D6.** About 25 rules added by the drafter with no Q/ADR source (reviewer 2 §3). Notable: the header CRC also in live sidecars and a reader refuses a bad one; the `camera_label` character set; a reader MAY play a live file; values ≥ 2^53 are an error in JS; track number < 128 as MUST; skellysync 16-bit; manifest audio items carry `sample_rate` and `channels`; a take anchor can still be written as INT64_MIN (should be forbidden); a shared `camera_label` is a warning, not a refusal.

## Dismissed

- "Two frames can lack a record after a crash" (reviewer 3 A11): measured 0–1 (`encoder_pairing` FINDINGS:185); the claim follows from the wrong SFF-402 wording.
- "Require bit-exact FLAC decode in SFT-252" (reviewer 3 B6): Electron 45 is bit-exact, but Electron 35 differs by up to 1.56e-5 (a float conversion, `flac_skau` FINDINGS §4). Keep the tolerance, or require exact on the integer path only.
- Frame rates above 1000 fps and `mach_absolute_time` timebase notes: real but minor; fold into the clock table text.
