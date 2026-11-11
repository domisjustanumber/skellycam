# GF04 notes (hw_accel_target, doc fix)

Date 2026-11-10. No tests, no timing, no device opened. FINDINGS.md was not edited. The proposed text is in `GF04_doc_fixes.md` (this folder) and `R/jellyfin_ffmpeg/gapfill/GF04_jellyfin_doc_fixes.md`.

## Files

| file | what |
|---|---|
| `GF04_doc_fixes.md` | items 1–7: old text with line numbers, then the new text |
| `GF04_capacity.json` | per scaling file: largest N that keeps up, CPU cores, unpaced fps, late frames, limit probe, affinity; single-stream rows for libx264/libx265 and nvJPEG fed decoded MJPEG |
| `S/hw_accel_target/gf04_capacity_extract.py` | parse-only script that wrote the JSON (`uv run --script`, no dependencies) |
| step3 scratchpad `GF04_src/` | libjpeg-turbo `LICENSE.md` (sha256 `ba6bceebcba0fdd35488477c2cca8c4632ce82c74dbfbc87d886ce6fc4433579`) and simplejpeg `LICENSE` (sha256 `dcb18a8aa6b52844c238b5266ccca7964793c74759092f6c004c34a90d7fe6d4`), fetched 2026-11-10 |

## Points for the saver

- The task's proposed line-387 wording did not match R1 and R4 as written:
  - R1 limits Annex L's patents to arithmetic coding and hierarchical lossless; it does not say "no patents listed in Annex L".
  - R4 is [measured] and says nothing about libjpeg-turbo.
  - So `GF04_doc_fixes.md` adds an R6 [source] for libjpeg-turbo's BSD-style licence and rewords the line.
- nvJPEG from NV12 at 1080p: in item 9, all reps keep up at N=8, with late frames 0, 73 and 66. `R/BENCH_RUN_2300_SUMMARY.md` §4 says "8 streams keep up, 16 do not". The unpaced aggregate at N=8 is 455.51 fps; the intra_compare §3.5 column reports N=16 (475). Both values are given.
- hevc_qsv after mjpeg_qsv decode (item 44): the N=1 unpaced median is 63.58 fps. intra_compare §3.5 gives 66 (66–67) at N=16. They are different N, and both values are in the JSON.
- nvJPEG 720p (item 54): 16 keep up, with 136 and 0 late frames over 2 reps.
- The K5 bug lines are `bench_encode_stream.py:54` (`mjpeg_qsv` → `nv12`), `:112` and `:119-124`. FINDINGS cited `:120-124`. The branch starts at `:119` (`if f.format.name == self.fmt`), and the limited-range reformat is `:123-124`.
- Still open, not part of GF04's edits:
  - `R/intra_compare/NOTES.md:179, 181, 208` stale cells;
  - `R/hw_accel_target/NOTES_functional.md:118, 120` "bit-identical" wording.
