# Prior art: open formats for synchronised multi-camera + microphone recording (2026-11-12)

Provenance: a sub-agent researched primary sources on the web (specs, official docs, project repos; generic queries, no private details); saved by the main session without re-checking each source. Claims the sub-agent could not verify from a primary source are marked [unverified]. Full source list at the end.

## Short answer

**No open standard does what the skellyfileformat design does**: per-device MJPEG video, FLAC audio, per-frame host and driver capture times, crash recovery and browser playback. **MCAP** comes closest as a general container; **Azure Kinect's MKV recordings** are the closest structural precedent; **XDF / Lab Streaming Layer** has the right clock model but is weak for video; **NWB** and **BIDS** are good export targets, not recording formats.

## Candidates

| Format | What / who / licence | Timing and sync | JPEG + FLAC? | Crash behaviour | Browser | Fit |
|---|---|---|---|---|---|---|
| XDF / LSL [1][2][3] | Multi-stream file from LabRecorder; spec GPL (SCCN) | Per-sample double timestamps on the sender's clock; ClockOffset chunks (collection time, offset) every 5–10 s, interpolated by importers; raw times kept, drift fit and dejitter at load | Binary samples possible; video metadata pages exist but no clear in-file video; no FLAC mapping | Boundary chunks (~10 s) to repair corrupt files; StreamFooter marks a clean close | Custom parser | Right clock model, weak for video |
| MCAP (+ ROS bag) [4]–[11] | Foxglove, MIT; ROS 2 default | uint64 ns `log_time` and `publish_time` per message | JPEG via CompressedImage (capture stamp); audio schema only PCM/G.711, FLAC needs a custom schema | Chunk CRCs, DataEnd CRC, optional summary; `mcap recover` rebuilds indexes | JS reader; no native media playback | Closest general container; one file per take; media tools can't read it [unverified] |
| NWB [12][13] | HDF5 neuroscience schema (maintainer/licence [unverified]) | `ImageSeries` external files + `starting_frame`; timestamps relative to `timestamps_reference_time` | Video external (lossy codecs allowed) | None (archival) | No | Export target |
| BIDS motion; BEP047 [14][15] | BIDS community | `acq_time` in `scans.tsv`; nominal `SamplingFrequency`; BEP047 (open PR) adds mp4/mkv/webm, no frame-level sync | Raw camera footage excluded (motion) | — | — | Export layout |
| SMPTE ST 12-1, MXF, BWF, OTIO [16]–[21] | SMPTE / EBU / ASWF | Timecode labels frames at nominal rates; cannot carry sub-frame capture times; BWF `bext` sample-accurate origin; OTIO references media with RationalTime | MXF multi-track, desktop-unfriendly | MXF growing-file behaviour [unverified] | No | Editor export (OTIO, timecode) |
| Matroska / WebM [22]–[24] | RFC 9559 | TimestampScale default 1 ms; block timestamps are 16-bit relative to the Cluster (finer scale forces shorter Clusters); BlockAdditions can carry per-frame data, including a registered ST 12-1 timecode mapping | `V_MJPEG` and `A_FLAC` registered | Live (unknown-size) segments must not use Attachments, Cues or SeekHead | MSE: no (MKV not an MSE format) | Our container |
| Azure Kinect recordings [25][26] | Microsoft, vendor (archived docs) | MKV with MJPEG colour, depth, IR and an IMU track of binary structs with µs timestamps; block timestamps = device time; `K4A_START_OFFSET_NS` tag restores the original start; tags record the multi-device sync setup | MJPEG yes; no audio | — | — | Nearest precedent |
| ISO BMFF (MP4) [27] | ISO | `tmcd` timecode, timed-metadata sample entries; `mjpg` and `fLaC` registered | Yes | Non-fragmented MP4 after a crash [unverified] | MSE yes (but no MJPEG in WebCodecs) | — |
| C3D [31] | Public domain, Motion Lab Systems | 3D points + analog; no video, audio or per-frame timestamps | No | — | — | Different purpose |
| Markerless tools [32]–[36] | Anipose, DeepLabCut, Pose2Sim, legacy FreeMoCap, Caliscope | Pair videos by name; Pose2Sim cross-correlates keypoint speed for unsynced cameras; legacy FreeMoCap and Caliscope use per-frame timestamp CSVs | — | — | — | No format, ad-hoc CSV/NPY |
| Frame-timestamp sidecars [37]–[40] | GoPro GPMF (`gpmd` KLV track, `TSMP` counter); Basler/GenICam chunk timestamps + frame counter + CRC; Android Camera2 timestamp source (REALTIME vs UNKNOWN) | Explicit timebase id per timestamp (Android); frame counters to detect drops | — | — | — | Ideas only |

Browser facts: MSE byte-stream formats are WebM, ISO BMFF, MPEG-2 TS and MPEG audio only [28]; the WebCodecs codec registry has no MJPEG video codec, FLAC is registered [29]; `ImageDecoder` support for a type is not guaranteed and must be feature-detected [30]. So MJPEG in any container needs a custom demuxer + `ImageDecoder` path in the browser.

## Conclusions (sub-agent)

1. **No existing standard already does this.** MCAP would give a mature spec, ns timestamps with two clocks per message, indexes, CRCs, a recovery tool and the ROS ecosystem, but loses ffmpeg/VLC readability [unverified], has no FLAC schema and puts a whole take in one file. Azure Kinect-style MKV is essentially this design. XDF has the right clock-offset model but poor video support and a GPL spec. **Keep the design and add exporters**: NWB (external files + timestamps), a BIDS/BEP047 layout with `acq_time`, OTIO for editors, optionally MCAP.
2. **Ideas to borrow:**
   - XDF: keep raw times immutable; explicit clock-offset records per clock pair (collection time, offset), interpolated at read time — relevant for future multi-PC rigs; periodic resync markers in live files; a clean-close marker.
   - MCAP: two named times per record (we have arrival and driver time); a file valid without its summary; a recover tool with lossless/lossy outcomes.
   - Android: a timebase id on every timestamp (we have `clock_id`).
   - GPMF/Basler: a device frame counter to detect drops (we have `source_frame_number`).
   - Azure Kinect: real times in block timestamps with the start offset in Tags; tags to identify tracks.
   - Matroska/broadcast: optionally an ST 12-1 timecode BlockAddition or BWF-style origin time from the take's UTC start, so editors line takes up for free.
   - NWB: one session reference time; `starting_frame` for split files.
3. **Possible mistakes the sub-agent sees:**
   - **Index container timestamps.** Every precedent stores actual capture time as the primary timestamp (Azure Kinect, ROS/Foxglove, NWB); with index timestamps generic tools show a fictional timeline when frames drop or the rate drifts, and `ffprobe` durations are wrong. *Main-session note:* this conflicts with our measured evidence (`results/EVIDENCE_INDEX.md` GF02): real timestamps in MKV made OpenCV miscount (888 for 891; 53,819 for 54,000) and miss seeks, while index timestamps gave exact OpenCV and freemocap reads in 18/18 files. See `vlc_playback_rate_20261112.md`. A decision for Dom.
   - **The sidecar as an end-of-file Attachment.** Legal, but not what Attachments are for, and absent after a crash. *Main-session note:* the design already keeps the live separate sidecar as primary until finalisation and embeds only into a finalised, known-size Segment (not live mode), so the crash case is covered; per-frame BlockAdditions were considered and rejected (Q20).
   - **The fitted lattice is derived data.** Keep raw times and record the fitter version and parameters so the fit can be redone. *Main-session note:* raw arrival and sample times are kept; recording the fitter version/parameters in the diagnostics JSON is a cheap addition.

## Sources

1. https://github.com/sccn/xdf/wiki/Specifications
2. https://labstreaminglayer.readthedocs.io/info/time_synchronization.html
3. https://github.com/sccn/xdf/wiki/Video-Compressed-Meta-Data
4. https://mcap.dev/spec
5. https://mcap.dev/
6. https://mcap.dev/guides/cli
7. https://github.com/foxglove/mcap
8. https://docs.foxglove.dev/docs/sdk/schemas/compressed-image
9. https://docs.foxglove.dev/docs/sdk/schemas/compressed-video
10. https://docs.foxglove.dev/docs/sdk/schemas/raw-audio
11. https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/CompressedImage.msg
12. https://nwb-schema.readthedocs.io/en/latest/format.html#imageseries
13. https://nwbinspector.readthedocs.io/en/dev/best_practices/image_series.html
14. https://bids-specification.readthedocs.io/en/stable/modality-specific-files/motion.html
15. https://github.com/bids-standard/bids-specification/pull/2231
16. https://pub.smpte.org/doc/st12-1/
17. https://pub.smpte.org/doc/st377-1/
18. https://www.loc.gov/preservation/digital/formats/fdd/fdd000013.shtml
19. https://www.loc.gov/preservation/digital/formats/fdd/fdd000356.shtml
20. https://github.com/AcademySoftwareFoundation/OpenTimelineIO
21. https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-timeline-structure.html
22. https://www.rfc-editor.org/rfc/rfc9559.html
23. https://www.matroska.org/technical/block_additional_mappings.html
24. https://www.matroska.org/technical/codec_specs.html
25. https://learn.microsoft.com/en-us/previous-versions/azure/kinect-dk/record-file-format
26. https://learn.microsoft.com/en-us/previous-versions/azure/kinect-dk/record-playback-api
27. https://mp4ra.org/registered-types/codecs
28. https://www.w3.org/TR/mse-byte-stream-format-registry/
29. https://www.w3.org/TR/webcodecs-codec-registry/
30. https://www.w3.org/TR/webcodecs/
31. https://www.c3d.org/ and https://www.c3d.org/HTML/Documents/thec3dfileformat.htm
32. https://anipose.readthedocs.io/en/latest/tutorial.html
33. https://deeplabcut.github.io/DeepLabCut/docs/Overviewof3D.html
34. https://github.com/perfanalytics/pose2sim
35. https://github.com/n1ckfg/freemocap (fork keeping the legacy FreeMoCap README)
36. https://mprib.github.io/caliscope/project_setup
37. https://github.com/gopro/gpmf-parser
38. https://docs.baslerweb.com/data-chunks
39. https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_7.pdf (cited for existence only)
40. https://developer.android.com/reference/android/hardware/camera2/CaptureResult

Not read: full texts of SMPTE ST 12-1, ST 377-1, ISO 14496-12, EBU Tech 3285, Apple QTFF timecode; the ROS 1 bag spec page blocked automated access.
