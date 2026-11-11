# GF05 notes: uncompressed_intra (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- measured (ffprobe 9.0.2, `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`): `chromium_samples/hevc_intra_420.mp4` is `profile=Rext`, `hvc1`, 1920x1080, yuv420p, 8 frames, all I.
- The "Main" label comes from `VERIFY_method.prev.md:28` (row R1), annotated in place. `VERIFY_method.md:28` does not carry it and was not changed.
- Proposed FINDINGS: §2.11 line 378 -> "libx265 all-intra 4:2:0 (Rext; generator declares hvc1.1.6...)".
