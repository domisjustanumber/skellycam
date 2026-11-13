# skellyfileformat spec v0: second sub-agent review (2026-11-12)

Provenance: three read-only sub-agent re-reviews of `skellyfileformat` `spec/SPEC.md` + `spec/conformance.md` at commit 7a2f821 (local), the same three angles as `spec_v0_review_20261112.md`: (1) layouts and internal consistency (fresh), (2) fidelity to Q1–Q26, D1–D6 and the active ADRs, with a fixed / partly / not-fixed check of every first-review item, (3) outsider implementability and testability (fresh). Merged and checked by the main session.

**Checked by the main session:** the conformance "How to read a test" section was broken by the revision script (it matched the inline `**SFT-001**` example first, replaced the rest of the section and the `## Tests` heading, and left the old SFT-001). Restored in its own commit (skellyfileformat, after 7a2f821). All other items below are open.

**Result of the fix check (reviewer 2):** all four first-review blockers fixed except the crash-state gaps listed here; all majors fixed or partly fixed; D1–D4 and D6 fixed; D5 partly (heading of §14 still says provisional over the final SFF-602). Reviewer 1 recomputed every table and the test values (camera_key 5443682299978691806, 501 ms tie, gap/repeat sequence, zero-record CRC) and found them correct.

## Must fix (clear fix)

1. **Crash safety, remaining gaps.**
   - `separate_final` is set in place (step 5): a torn write breaks `header_crc32`, and SFF-152 then refuses the only final sidecar. Write it through `.tmp` and a rename. (all three)
   - The `.mka` is renamed at step 4 but verified only at step 7, after the `.skat` is deleted; a reader would use a bad `.mka`. Verify the `.mka` (frame CRCs, decoded sample count) in step 2, before any rename. (2)
   - §9.7 row 2 cannot be told apart from a plain UID mismatch, because readers ignore `.tmp`. Let a reader note that `<media>.tmp` exists (name only) and report `needs_recovery` only then. (2, 3)
   - Audio row for "finalised `.skat`, no `.mka`, only `.mka.tmp`, plus `.flac` + `.skat.live`" is missing; the audio row 6 overlaps row 3. (1, 3)
   - The appender's SeekHead rewrite (step 3) can tear; SFF-363 restores only the Segment size. Restore the SeekHead span without the Attachments entry; detect a torn span by an EBML parse failure or a CRC-32 element mismatch. (3)
   - Verify failure during recovery (rows 5, 6), a CRC mismatch in normal finalisation step 2, and an interrupted recovery (must be repeatable from every state) are not covered. (3)
2. **Reader states.** Add a state column to §9.7; add a `legacy` state (SFF-551 uses it); tests use labels SFF-666 does not define ("live, no frames", "in format, finalised", "unsupported version"). Give refusal reason codes (SFT-170 "same reason"). Header check order must be magic → major → `header_size` bounds → CRC → the rest of SFF-179 (the CRC location needs `header_size`). (1, 2, 3)
3. **Small contradictions.**
   - SFF-401 and SFF-361 need the live `.flac` exception of SFF-550. (1)
   - SFF-357 for audio must use packet records and `table_count`. (1)
   - SFF-113 "each media file" includes the `.flac`: say "each Matroska media file". (1)
   - SFF-453 keeps frames with a matching CRC, which can leave a sample gap (breaks SFF-256): truncate at the first mismatch. (3)
   - `adc_ns` behaves like the time of sample `sample_index + frames` (digest §7, AC §4.1); the drift fit as written is off by one block. (2)
   - A newer reader must read a field only when the file's `minor` is at least the minor that added it (else it reads JSON bytes as fields). (3)
   - Folder opening: say which files are candidate media files (non-`.tmp` files that start with the EBML magic `1A 45 DF A3` or `fLaC`). (3)
   - Room rule for the appender: R = span − new SeekHead length; R = 0 no Void, R = 1 widen, R ≥ 2 Void, R < 0 refuse; the CRC-32 element is the first child. (3)
   - README Scope: the separate sidecar is also final when the appender refuses. (2)
   - ADR-FGK2 item 7 first sentence and the record-growth / `type`-field rules have no SFF ID. (2)
   - §14 heading says provisional, but SFF-602 is final (D5). open-work.md lacks the T-S7 and A3 items that SFF-165 and SFF-251 cite. (2)
   - Flag tables should show their reserved bit ranges; SFF-179's JSON check must match SFF-153's range and include the drift table in the overlap check; the scan must filter blocks by track. (1, 3)
4. **Tests.**
   - SFT-351 must say step 7, not step 6. SFT-600 must copy SFF-600 ("minus the first source frame"). SFT-601 needs the expected value and corner colours (and the FFmpeg display matrix is counter-clockwise). SFT-300 must be provisional. (1, 2, 3)
   - Writer halves: add writer output to SFT-150, SFT-161 and SFT-250. Reader side of the SFF-454 audio states. (2, 3)
   - SFT-001 known-answer CRC: CRC-32 of `123456789` = 0xCBF43926. SFT-151: wrong magic with a bad CRC. SFT-352: the CRC-32 SeekHead input and a write/flush trace. SFT-361: build each §9.7 row by a script, not by random kills. SFT-107: same pixels with different timestamps give byte-identical JPEGs. SFT-453: name the seed. SFT-165: an accuracy bound against the known lattice. Tests that change a golden file must recompute its CRCs (SFT-153, SFT-168, SFT-360) or name the attachment (SFT-170). SFT-661: also start times, `utc_offset_min`, `group_size`. G12 also through the appender and the scan. (1, 3)

## Decisions for Dom

- **E1.** Gap after an encoder skip (SFF-170 contradicts itself): set `gap` too (the frame number jumped) and add `encode_skip` (why), or define "previous" as the last frame received including skipped ones?
- **E2.** Recovery when a record in the middle has no matching block: keep the longest paired prefix (stop at the first mismatch, like Q8), or renumber `write_index` and the timestamps?
- **E3.** Live offsets with small JPEGs: reviewer 3 says FFmpeg's Matroska muxer buffers a whole Cluster in memory and starts a new Cluster only past about 4 KiB, so offsets from the file size can be wrong for frames of 4 KiB or less. Our one-behind measurement (2,699/2,699) used real camera frames. Not yet checked against the pinned PyAV/FFmpeg. Run a desk test (tiny JPEGs) before gate 2, and if it fails, require the writer to end the Cluster after each frame?
- **E4.** Windows renames and power loss: on Windows a rename over a file that a reader holds open fails. Readers read a sidecar whole and close it; writers retry a failed rename and stay in the previous §9.7 state. Is power loss in scope? Proposal: conformance covers process kills; writers SHOULD flush the folder after renames on POSIX; power loss is not tested.
- **E5.** Audio timing with no ADC times (common with WASAPI through PortAudio): no drift table is written, and nothing maps samples to the host clock. Proposal (provisional): a linear fit of `host_ns` against `sample_index`, stored in the same drift table with a flag.
- **E6.** SFF-207 (the `.mka` has the stem of its `.flac`) is a file-name rule, against ADR-WD1R item 5 and ADR-25VV item 2. Withdraw it and pair the audio files by `take_uuid` (one audio file per take)?
- **E7.** WebCodecs decode (SFT-252): two reviewers ask for bit-exact samples (FLAC is lossless). Proposal: bit-exact when decoding to 16-bit integers; within one 16-bit step for float output (Electron 35 measured 1.56e-5 from the conversion).

## Other notes

- FFmpeg writes no SegmentUID in bitexact mode (reviewer 3, from memory of matroskaenc; not checked here). The golden files must be made without `+bitexact`, or with the UID patched after muxing. A Matroska file with no SegmentUID matches no sidecar.
- New rules in the revision with no source (reviewer 2 §4) are all minor and listed there: SFF-005 ms precision for UTC, SFF-006 UTF-8 cut, SFF-104 1000 fps limit, SFF-660 `group_position`, SFF-665 order, SFF-667 first camera's values, SFF-668 two manifests.
