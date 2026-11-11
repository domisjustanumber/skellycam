# GF07 notes: Intel Windows encode sources (2026-11-10)

Main file: `GF07_intel_windows_sources.md`. Excerpts and sha256 values: `GF07_sources/`. No tests, no timing, no camera.

What changed:
- intel.com and edc.intel.com now return the raw pages to curl when the request carries a browser user agent and Accept/Sec-Fetch headers (`step3/GF07/tools/fetch.sh`). The 2026-11-09 WebFetch transcriptions can therefore be replaced by verbatim quotes.
- Windows-specific Intel sources now exist for:
  - H.264 and HEVC encode on RPL, MTL, ARL-S/HX, Arc A and Arc B;
  - HEVC 4:2:2 encode on RPL (shader-assisted), MTL, ARL-S/HX, Arc A and Arc B;
  - JPEG encode on RPL, MTL and ARL-S/HX.
- LNL is covered only by a datasheet whose page is labelled "Confidential". Dom should decide whether it can be cited.
- Still NOT VERIFIED on Windows: Arc B JPEG encode; ARL-H/ARL-U codec list; LNL HEVC 4:2:2.
- New disagreement: MTL/ARL-S HEVC 4:2:2 encode is Y in Intel's Windows sources (datasheets, KB 000098345) but "D" only in the Linux media-driver README. So the FINDINGS cell "4:2:2 enc N" is a Linux statement.
- I5 (F/KF) re-sourced:
  - oneVPL doc: "Intel® Core™ Processors without processor graphics do not have media support.";
  - suffix table: "F | Requires discrete graphics";
  - ark 265KF: "Intel® Quick Sync Video | No";
  - measured: no GPU section on the 10400F, 11900KF, 12400F and 14700KF pages.
- Bonus for J6: Intel's 2021 encode/decode article says "no limitation on the number of concurrent sessions to transcode" for the graphics it lists (Iris Xe MAX, 7th–11th Gen only).
- Transcription errors found and listed in §3 of the main file. The main one: the transcript lost the MJPEG 4:2:2 and 4:4:4 encode rows from the oneVPL summary tables.
