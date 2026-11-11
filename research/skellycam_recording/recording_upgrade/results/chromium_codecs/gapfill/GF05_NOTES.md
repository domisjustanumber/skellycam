# GF05 notes: chromium_codecs (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- Proposed: §5 replaced by pointers to the intra_playback timed results; P2 closed (JPEG path at N <= 8 measured, camera-byte timing NOT VERIFIED); P3 extended (WebCodecs master clock vs stalled `<video>` at N = 8); P4 "requirement 9" -> "requirement 3"; §8 queue row superseded.
- Evidence: `GF05_intra_playback_extract.json` (from `scripts/chromium_codecs/gf05_extract_intra_playback.py`), `GF05_ffprobe_hevc_intra_420.txt`.
