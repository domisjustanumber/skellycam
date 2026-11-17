# Spec v0 revived: MKV/MKA with timing and tracking sidecars (proposal)

Status: proposal for Dom's review, 2026-11-13. Dom decided on 2026-11-13 to reverse D27 and return to spec v0 (MKV/MKA) with sidecars; everything else here is proposed.

Written for: Dom and future agent sessions working on skellyfileformat and freemocap development-streaming.

**Nothing here is accepted.** Agents filled in every choice, and Dom decides. No code was written and no tests were run for this report. All citations come from read-only reading of code, spec text and results files. Anything without a citation is marked "not verified".

Citation keys (full list in the Evidence section):
- **S** = SFF `bd62b60:spec/SPEC.md` (spec v0 rev 2). **C** = `bd62b60:spec/conformance.md`. **E/<id>** = SFF `decisions/entries/<id>-*.md` on main. **OW** = SFF `38ad0d6:decisions/open-work.md`.
- **FMC** = freemocap `upstream/development-streaming` @c27fc299. **SCds** = skellycam `remotes/upstream/development-streaming`. **A73** = Blender addon commit 73e1b3e, the commit FMC locks (FMC:uv.lock:783-785). It was read from the uv git cache (`%LOCALAPPDATA%\uv\cache\git-v0\db\bc66ecde1d0b8425`). **INST** = the installed addon in FMC\.venv (main @980ae856).
- **EI** = `SC\research\skellycam_recording\recording_upgrade\results\EVIDENCE_INDEX.md`. **RES** = that results folder. **R3** = `SC\research\skellycam_recording\docs\spec_v0_review3_20261112.md`. **TFD** = `docs\tracking_file_decisions_20261113.md`. **HO** = `SC\research\HANDOFF_20261113_freemocap_phase2_work_items.md`. **PLAN** = `SC\research\CAPTURE_AND_RECORDING_PLAN.md`.

---

## Summary

**What changes from MCAP spec v1**
- MCAP, protobuf, the foxglove schemas, topics, chunk CRCs, chunk-cut repair and the Lichtblick layout all go away (E/DK8S items 1, 3-6, 10; E/PV6S items 1-4; E/WD9A).
- Lichtblick stops being the viewer. No test has ever opened an MKV in Lichtblick: no script under `scripts\lichtblick_check`, `scripts\tracking_sync` or `scripts\mcap_*` mentions MKV or Matroska (grep rc=1).

**What comes back from v0**
- One MJPEG `.mkv` per camera with **index (constant-rate) PTS** (S:160-163, SFF-104).
- A `.skvt` binary timing sidecar per camera and a `.skat` for audio (S §5, §7).
- The u16 versioning (SFF-050..053), the clock table (S:315-320) and the take facts in every header (SFF-650).

**Proposed changes against v0** (all proposals, not decisions)
- Proposed: sidecars are **always separate files and never embedded** (Decision 1). This removes v0 §9's appender and the embed crash rules, where 4 of the 8 review-3 blockers sat (R3:9-12; E/SFK5:42-44).
- Proposed: the `.mkv` and `.mka` hold **only** video or audio plus container timestamps. There is no audio track inside a camera MKV, unlike v0 §8 (S:598-618).
- Proposed: **the 2D and 3D tracking sidecar is freemocap's existing `<rec>_data.parquet`**, reused (FMC:freemocap/core/recording/sample_encoding/arrow_schema.py:15-29) (Decision 11), with take and camera links added (§5).
- Proposed: port the container-independent content of the accepted MCAP-era entries: WG08 reader states, MG7C/T24G fit rules (option), 752H time meanings, PV6S repair consent, 5G42 repair marker, TDB5 no-manifest and 7K3C versioning.
- Proposed: the Blender addon reads the `.mkv` after a suffix patch, **if** DT-B1 shows that Blender decodes MJPEG MKV with frame_duration = N. **Not verified.** That is the gating test, and Blender is the reason for the reversal.

**Corrections to earlier facts (all cited)**
- The installed addon is the stale `main` build 980ae856 (INST `direct_url.json`). FMC locks 73e1b3e (FMC:uv.lock:785), and `git diff --stat 980ae85 73e1b3e` shows 176 files changed. The `.mp4` filters in 73e1b3e are at A73:core_functions/load_videos/load_videos.py:12-13, add_capture_cameras.py:142 and parquet_scene.py:161,165 (re-read for this report: :161 selects the folder only if it holds a `.mp4`, :165 lists only `.mp4`).
- `recording_framerate.py` has no callers (`git grep` finds only its own definition). The posthoc filter rate is 1/median(diff(timestamps_s)) (FMC:freemocap/core/reconstruction/posthoc_filtering.py:50-56), fed from group timing (FMC:freemocap/core/tasks/mocap/posthoc_mocap_task.py:237-245).
- GF02's "FreeMoCap reads OK" used the `development` reader (cv2), not dev-streaming's PyAV `SequentialVideoReader` (scripts/jpeg_passthrough/jp_io.py:353-363; FMC:freemocap/core/pipeline/posthoc/video_group_helper.py:14,149,188).
- Posthoc 2D **is** saved on dev-streaming, as OVERLAY_2D in the Parquet (FMC:freemocap/core/recording/result_processing/observation_inputs.py:212-225). HO:38 is wrong for that branch.
- skellycam's default video writer is `cv2.VideoWriter` with fourcc X264. `PyavVideoWriter` is only the fallback for when OpenCV has no H.264 (SCds video_recorder.py:120-134; fourcc_codec_helpers.py:13-16; camera_config.py:29). See §2.

---

## 1. Take folder layout

**Proposed (reuse-first): keep `synchronized_videos/` and today's file names.**

```
<rec>/
  <rec>_info.json                    skellycam take info (kept, changed: §7)
  <rec>_recording_info.json          freemocap info (kept)
  <rec>_camera_calibration.toml      (kept)
  <rec>_data.parquet                 2D + 3D tracking sidecar (kept, links added: §5)
  synchronized_videos/
    <rec>.id-<cam>.idx-<i>.mkv       video only
    <rec>.id-<cam>.idx-<i>.skvt      timing sidecar, one per camera
    <rec>.audio.mka                  audio only
    <rec>.audio.skat                 audio timing sidecar
    synchronized_videos_README.md    (kept)
  annotated_videos/, exports/, <rec>.blend      freemocap derived output (kept)
  output_data/charuco_observations_realtime.pkl (kept for now: §7)
```

Evidence:
- skellycam writes `synchronized_videos/` today (SCds:skellycam/core/recorders/videos/recording_info.py:47-50; SCds:skellycam/system/default_paths.py:6-8).
- The folder name is hardcoded in at least seven FMC production sites: video_group_helper.py:385; playback_router.py:263; mocap_router.py:337; calibration_router.py:181; freemocap/system/default_paths.py:12; saved_observations.py:73; recording_structure.py:141 (`git grep` on FMC). It is also in the dataset tools (freemocap/tools/datasets/catalog.py:36, preparation.py:364, scientific_comparison.py:122, stage_matrix.py:200, workflow.py:173, full_recording_comparison.py:43,46), in the Electron and UI code (freemocap-ui/electron/main/api.ts:307,364; layout-presets.yaml:25; recording-structure.ts:141,151) and in the addon (A73 parquet_scene.py:160-165,204,220-226).
- The declared layout `videos/synchronized/` (FMC:freemocap/system/recording_structure/recording_structure.py:88-132) is never written. `create_on_disk()` has no production caller (git grep), and saved_observations.py:73 falls back to `synchronized_videos/`. The contract audit admits the gap (FMC:current-work-plans/03-transport/recording-folder-contract.md:33-53).
- The video name pattern is SCds:skellycam/core/recorders/videos/video_filename.py:7. `.mkv` is already in every VIDEO_EXTENSIONS set: FMC:freemocap/core/playback/media_selection.py:8; FMC:freemocap/system/recording_status/recording_status.py:20; SCds video_filename.py:8; and Electron's freemocap-ui/electron/main/api.ts:26.
- `.mka`, `.skvt` and `.skat` are in none of those sets, so video discovery skips them (same citations).
- Media and sidecars side by side in one folder matches v0 (S §12 `<stem>.skvt`; SFF-654).
- New takes have no `synchronized_videos/timestamps/` subfolder (see §4).

**Cleaner option:** change the declarations in `recording_structure.py:88-132` and `shared/recording-contract/paths.json:3-24`, plus the contract doc, so they match what is written. Cost: constants and a doc only. Moving the files to `videos/synchronized/` would instead touch every site listed above, skellycam `default_paths.py`, the UI and the addon. Proposed: fix the declaration and do not move the files.

---

## 2. MKV video

**Inside** (v0 §4 minus the embed rules):
- Exactly one V_MJPEG track (SFF-100, S:146-148). One JPEG per SimpleBlock with the keyframe flag set and no lacing (SFF-101). Camera bytes unchanged (SFF-102). For a camera that sends raw frames, v0 encodes each frame to JPEG (SFF-102, S:153-154; see §2a).
- Track number below 128 (SFF-107). A random non-zero SegmentUID (SFF-113).
- No timing data inside a JPEG (SFF-111, S:187-188). No overlays or burned-in text (SFF-110; E/W4PF items 5-6).
- Rotation: see §9. Under v0 there is no container rotation element (SFF-103, S:156-158).

**Not inside:** Attachments, Chapters, tags beyond what the muxer writes, a rotation flag, or any audio track. SFF-105/106 (SeekHead room, no Attachments) are deleted, because they exist only for the embed (S:164-170).

**PTS = frame index** (SFF-104): frame k is at k × den × 1000 / num ms, and measured times are forbidden (S:160-163). Evidence:
- With index PTS, the OpenCV 4.12 count, 11/11 POS_FRAMES seeks and FreeMoCap reads were exact in all 18 index files, including drops and a 54,000-frame file (EI:53; RES\crash_resilience\gapfill\GF02_container_matrix.json partA[]).
- With real PTS, OpenCV miscounted 888/891 and 53,819-53,820/54,000, and seeks missed (EI:54; GF02 partA[]).
- `recover()` on a real-PTS MKV wrote r_frame_rate 125/2 (62.5 fps) in 12/12. Index-PTS MKVs recovered with the correct count (EI:110; GF02_recovered_rates.txt).
- Today's skellycam writers:
  - The PyAV fallback writes pts = frame index at rate int(round(fps)) (SCds pyav_video_writer.py:14,33). Its docstring says it is used on Linux when OpenCV lacks libx264 (pyav_video_writer.py:4-6). Because of the rounding, a 29.97 fps take would be written at 30.
  - The default path is `cv2.VideoWriter(path, fourcc, framerate, shape)` (SCds video_recorder.py:129-134), default fourcc X264 (camera_config.py:29). It is constant-rate by API design, but the container timestamps it writes are **not verified** (desk test DT-P1: ffprobe the packet pts of a Windows skellycam MP4).
  - The VFR remux is commented out (SCds recording_finalizer.py:63).
  - Therefore: if DT-P1 confirms index PTS, frame-index meaning does not change for freemocap readers. Until then, that is not verified.
- Caveats:
  - The writer in every test was PyAV 19.0.2 / FFmpeg 9.0.2 (EI:40). FMC locks av 18.1.0 or 19.0.1 (FMC:uv.lock:123-128,147-152), and skellycam declares `av>=18.1.0` (SCds pyproject.toml:68). Not verified on those versions.
  - Only 30 fps was tested. 30000/1001, 59.94, 60 and 120 are not verified (DT6).
  - The "FreeMoCap read" was the development reader (see Summary). Not verified on dev-streaming (DT1).
  - All results come from one Windows 11 machine (RES\crash_resilience\FINDINGS.md:5-6; EI:40). Linux and macOS are not verified (DT-X1).

**Nominal rate:** rational, num and den from 1 to 2^20, else `bad_rate` (E/752H item 7, 752H:30-31), plus v0's 1000 fps cap so the 1 ms timestamps strictly increase (S:162-163). The bound also settles review-3 F6 and the SFF-104 overflow item: write_index is u32 (S §5.4 record table), so k × den × 1000 < 2^32 × 2^20 × 2^10 = 2^62, and the rounding term adds less than num ≤ 2^20, which fits in u64 (arithmetic, no test needed).

**Muxer settings (proposed default):** `flush_packets=1`, with byte offsets filled in at finalisation by a scan.
- With fp, an MKV lost exactly 1 frame per kill in 12/12 (GF02 partB[].lost_vs_sidecar). On a drained kill at 55.4 KB/frame, MKV without fp kept 146/150 frames and its size was a multiple of 262,144 B; with fp it kept 149/150 (RES\crash_resilience\pyav19_recheck.json kill[]; RES\crash_resilience\FINDINGS.md:52-58).
- Cost of fp: +4.9 µs/frame (RES\crash_resilience\bench\fragment_overhead_mjpeg_pyav19.json; CR FINDINGS.md "flush_packets=1 on MKV adds 4.9 µs/frame").
- Offsets by scan cost 63 ms (PyAV packet.pos+4) to 112 ms (EBML walk) per 18,000 frames, warm cache, 18,000/18,000 correct (RES\sidecar_embedding\audio_offsets.json S5).

**Cleaner option (live offsets, v0 SFF-402):** add `cluster_size_limit=1` so every frame is its own Cluster, and write offsets live.
- With small JPEGs, the live-offset rule held for only 37-149 of 299 frames without the limit, and for 299/299 with it (RES\sidecar_embedding\small_jpeg_offsets.json; sidecar_embedding\FINDINGS.md:255).
- Size: with real-size JPEGs (640×360, about 28 KB) the file is byte-identical with and without `cluster_size_limit=1`, because FFmpeg already writes one Cluster per frame. With 160×90 JPEGs the limit adds about 15 B per extra Cluster (613,562 → 616,274 B) (docs\vlc_playback_rate_20261112.md:34). The fragment_overhead bench tested `cluster_size_limit=0` + `cluster_time_limit=0`, not `cluster_size_limit=1` (CR FINDINGS.md:58).
- Inferred, not verified: for all-key payloads over 4 KiB/frame every frame already opens a new Cluster (CR FINDINGS.md:386, from FFmpeg source), so GF02's 55 KB-frame index files were probably already one Cluster per frame. DT5 therefore matters mainly for small frames.
- Gain: a live or crashed file can be read by byte range through the sidecar.
- Cost: OpenCV count and seeks on one-Cluster-per-frame files with small frames are untested (sidecar_embedding\FINDINGS.md:255), and SFF-402/403 stay in the spec.

**Live and crashed files:**
- An unfinalised MKV gives an OpenCV 4.12 FRAME_COUNT of −2.767e17, and POS_FRAMES seeks silently return frame 0 (EI:109; GF02 partB[].killed_cv2).
- skellycam's VideoFileMetadata, which FMC uses, rejects counts below 1 (SCds:skellycam/core/recorders/videos/video_file_metadata.py:35-36). freemocap must therefore only see finished or repaired files. Today FMC's status code counts videos by extension alone (FMC recording_status.py:170-176), so it would count a killed `.mkv` (proposed flow: §4i).
- Repair: a PyAV remux runs at 0.907 s/GB and kept 17,617/17,618 frames (RES\crash_resilience\bench\repair_pyav19.json). Repair runs only after the user agrees (E/PV6S item 7), and the file is marked repaired (E/5G42 item 1).
- A remux changes the SegmentUID and moves every frame (0/1,800 offsets unchanged; audio_offsets.json S6). Repair must therefore rewrite the sidecar's `segment_uid` and offsets (SFF-400).
- An in-place MKV repair that never rewrites bytes before the cut (E/PV6S:28-29) is not verified.

### 2a. Non-MJPEG capture (new section)
The freemocap UI offers capture and writer fourcc choices of MJPG, X264, YUYV and H264 (FMC freemocap-ui/src/store/slices/cameras/cameras-types.ts:18,59-60). skellycam's default capture fourcc is MJPG and the default writer fourcc is X264 (SCds camera_config.py:28-29).
- Proposed: the writer fourcc option goes away for new takes (the writer is always MJPEG in MKV). For a camera captured as YUYV, the writer encodes to JPEG as v0 says (SFF-102), and `encode_skip` keeps its v0 meaning (S:364; SFF-171). H264 capture: refuse it for new takes, or decode and re-encode it to JPEG. Open (Decision 23).
- JPEG encode throughput for YUYV cameras at the target rates is not verified (DT-E1).

---

## 3. MKA audio

Context: freemocap reads no skellycam audio today. A grep finds only `mic_device_index=-1` (FMC calibration_router.py:133; mocap_router.py:49,89), and skellycam records audio only when the index is ≥ 0 (SCds:skellycam/core/camera_group/camera_group.py:207). So no freemocap reader can break.

**Proposed default (reuse-first): FLAC, as in v0 §6.** Native `.flac` while recording, written with `frame_size=1024` and `flush_packets=1`, then a stream copy into a `.mka` with one A_FLAC track at finalisation. CodecPrivate is `fLaC` + STREAMINFO only (SFF-200), and audio PTS comes from first_sample (SFF-206).
- Native FLAC with `frame_size=1024` lost 0 ms per kill in 12/12. At the default 4608-sample frames it lost 11-85 ms (RES\audio_skellycam\FINDINGS.md §2.2 table; crash_kill.json). So `frame_size=1024` must be part of the writer rule.
- Of those 12 kills, 6 were `os._exit(1)` inside the child and 6 were `p.kill()` (TerminateProcess) from the parent (audio_skellycam\FINDINGS.md §2.1; scripts\audio_skellycam\crash_kill.py:60-68). Whether the killed process was the writer or a launcher is not verified for the TerminateProcess half (compare RES\mcap_kill\FINDINGS.md "Problems found" 1).
- The `.flac` → `.mka` copy was byte-identical, 1,407/1,407 frames, and killed files needed no STREAMINFO patch (RES\flac_skau\flac_skau.json, recovery_check.json).
- Live-sidecar kill test: 0 torn records, exact-prefix recovery in 40/40 (RES\flac_skau\FINDINGS.md §8). Caveat: `Popen.kill` probably killed the uv launcher, not the writer (RES\mcap_kill\FINDINGS.md "Problems found" 1).
- VLC 3.0.24 drops the last 26.7 ms of a native `.flac` but plays the `.mka` complete (RES\flac_skau\vlc_check.json; flac_skau\FINDINGS.md:76-80). The `.mka` files tested had the `.skau` sidecar embedded as an attachment. A plain `.mka` with no attachment, which this proposal writes, is not verified (add to DT-A2).
- WebCodecs decoded FLAC fetched by offset sample-exactly in E45 (RES\flac_skau\electron_e45.json).
- Cost: it supersedes E/D9N1 (accepted 2026-11-13, D9N1:3), and it keeps the `.flac`/`.skat.live` delete step, which is review-3 blocker B2 (R3:10). Size: 172.0 MB/h for mono FLAC level 5 in a native `.flac` file, synthetic signal (RES\audio_skellycam\bench.json). MKA size not measured.

**Cleaner option: Opus written straight into `.mka`** with the D9N1 settings (48 kHz, 20 ms packets, VBR 128/256 kbit/s; E/D9N1:17-19) and `cluster_time_limit=100`.
- Gain: it keeps the accepted D9N1, and there is no intermediate file (B2's audio deletes and SFF-204/208 go away). Matroska carries pre-skip natively as A_OPUS CodecDelay (docs\mcap_check_20261113.md:93, a source-only claim, not tested).
- Size: the bench measured Opus only in Ogg: 25.1 MB/h mono at 64 kbit/s and 52.0 MB/h at 128 kbit/s (bench.json). Size at D9N1's 128 kbit/s mono / 256 kbit/s stereo in MKA is not verified (DT-A1). By arithmetic it is about twice the 64 kbit/s figure.
- Cost: with `cluster_time_limit=100`, 117-137 ms (median 122) was lost per kill, 12/12 readable. With default settings, 317-3,691 ms was lost and 6/12 files had no audio (audio_skellycam\FINDINGS.md §2.2 table).
- VLC ignores the codec delay (+312 samples; audio_skellycam\FINDINGS.md §2.2 offset table).
- Tests ran at 64/96 kbit/s, not D9N1's 128/256 (audio_skellycam\FINDINGS.md:21). Live packet offsets in MKA Opus are not verified. Live offsets are proven only for native FLAC, 1,408/1,408 (flac_skau.json).

In both options the `.mka` holds exactly one audio track. Sample-accurate host times live in the `.skat` (§4).

skellycam's current `<rec>.audio.wav` + `audio_timestamps.json` (SCds:skellycam/core/recorders/audio/audio_recorder.py:121-162) are replaced for new takes. No FMC reader exists (FMC mocap_router.py:141,237).

---

## 4. Timing sidecars (`.skvt` per camera, `.skat` for audio)

**4a. Embedded or separate.** "mkv and mka files would be just video, audio, and timestamps" has three readings:
- (i) container PTS only, with the timing table in a separate file;
- (ii) the timing table embedded as an attachment (v0 §9);
- (iii) real capture times as the PTS.

(iii) is ruled out by evidence (EI:54,110). **Proposed: (i), never embed.** This removes SFF-105/106, SFF-352..363, finalisation steps 5-6, the `separate_final` flag, crash rows S:741-743, and review-3 B1, B3 and B4. The accepted cost is the one ADR-3KH3 named: "A separate file can become lost" (E/3KH3:39). A lost `.skvt` leaves frames with no times (SFF-553). The SegmentUID check still catches a remuxed media file (SFF-401; audio_offsets.json S6).

**4b. Format: v0 binary, a CRC per record, as a separate file (proposed).** The trade-off, stated plainly:
- Kill survival is the same. Under process kill, a CSV flushed per row and binary records with CRC and flush both kept 1/37/500 rows. With default buffering, both lost rows (RES\crash_resilience\sidecar_durability.md, "Process kill" table).
- Truncation is the same for a strict parser. Over 24 cuts × 2 tails, the strict CSV parser and the CRC parser recovered exactly. `pandas.read_csv` returned an extra row in 23/24 cuts, and in 6/24 looked complete but held wrong values (sidecar_durability.md, truncation table).
- What binary adds:
  - Per-record CRC corruption detection. With one byte changed, only the CRC format rejected the record (RES\overlays\verify_method_crash_modes.json). That test covered the `.skov`, JSONL and MessagePack overlay formats, not CSV.
  - Fixed-size records for byte-range lookup. Electron loaded 16 cameras × 1 h of 64 B records in 95-107 ms at 30 fps (RES\sidecar_load\summary.json).
- What CSV adds: a live CSV flushed per row could keep the existing reader (SCds recording_timing_reader.py:80-117) unchanged.
- The remaining argument against CSV is policy: D19 / E/X1G6 say new takes write only the new format. The crash evidence does not decide it. So Decision 2 is a policy and corruption-detection choice.
- Today's CSVs are written only at finalisation (SCds recording_finalizer.py:53-61), so a crash leaves no timing. That is a property of the writer, not of the format.
- Parquet: FMC writes it only atomically at the end (FMC:freemocap/core/recording/parquet_storage/parquet_writer.py:69-90), so it is not appendable live.

**4c. How freemocap finds and reads it: reuse the existing seam.**
- skellycam already declares timing paths in `_info.json`: `camera_timing` {camera_id: path} and `multiframe_timing` (SCds recording_info.py:86-97). Readers find timing only through these fields (SCds:skellycam/core/timestamps/recording_timing_reader.py:18-31).
- Proposed: point `camera_timing` at the `.skvt`, and make `read_recording_timing` dispatch on the suffix. The change lives in the skellycam package freemocap already imports. The `.skvt` parser would come from skellyfileformat, as an exactly pinned dependency (Decision 22).
- Callers that then work unchanged: FMC recording_timing.py:20-48 and playback_router.py:79-84,793-803.
- Callers that need edits:
  - FMC video_node.py:496-509 reads the CSV columns `recording_frame_number` and `connection_frame_number` directly. It needs the sidecar's `source_frame_number`.
  - SCds recording_statistics.py:13-23.
- Reader requirements the `.skvt` must meet:
  - frames == range(frame_count) (recording_timing_reader.py:65). This holds if write_index runs 0..N-1.
  - Times strictly increasing (recording_timing_reader.py:105-112). v0 promises only "never decreases" (SFF-177). **The spec must state strictly increasing, or the reader must handle ties.** Whether ties occur is not verified.
- Which `.skvt` time RecordingTiming returns is open (Decision 16). Today's CSV main time is (pre_grab + post_grab) // 2 (SCds create_camera_csvs.py:50-51).

**4d. Header** (v0 §5 with the later entries folded in):
- Take facts in every header: take_uuid, take_start_host_ns, take_start_utc_ns, utc_offset_min, group_size (cameras only), clock_id (SFF-650, SFF-652).
- segment_uid (SFF-400/401), nominal_rate num/den (§2), display_rotation (SFF-159) and camera_label.
- camera_key as a **MUST**, not v0's SHOULD (SFF-162; TFD Q42 at TFD:62). Never a raw serial (E/DK8S item 8; SFF-653).
- group_position, i.e. the grid order (S:282-293; TFD Q36).
- Version as u16 major/minor/prerelease (SFF-050..053) with E/7K3C meanings: release major.minor, refuse an unknown major, read a higher minor.
- Clock ids per v0 §5.3 (S:315-320; E/752H item 3). Ids 2 and 3 are still provisional pending T-S7 (SFF-165; OW:34-43).
- The 160-byte common header, header_crc32 and body_crc32 (S:204-234; SFF-151, SFF-157/158).

**4e. Per-frame record** (v0 64-byte record, S:333-345):
- Keep: arrival_ns; sample_time_ns with INT64_MIN = absent (SFF-003; E/752H meaning); source_frame_number u32 mod 2^32; write_index; offset, size, jpeg_crc32, record_crc32; and the flags gap, repeat, encode_skip, fit_valid, fit_unreliable, offset_state and recovered (S:358-370).
- Drop `legacy_ns` ("The legacy time had no reader", E/752H item 4, 752H:39).
- `encode_skip`: keep its v0 meaning for raw-capture cameras that the writer encodes (SFF-102, SFF-171; §2a). It is never set for MJPEG passthrough.
- New flag (proposed): **`filled`** in reserved bit 3 (S:365 "reserved, always 0"), for a grid position the writer filled (§8). This is a change to v0, not a reuse. v0's `repeat` means the camera re-delivered the same source_frame_number (S:362; SFF-170) and must keep that meaning.
- Breakpoints are not needed: they existed because the MCAP summary had no `sequence` (E/MG7C:39-40), and every record here stores `source_frame_number`.

**4f. Fit.** Default (reuse-first): v0's per-record `fitted_ns`. Player time = fitted when the file is finalised and every record has fit_valid, else arrival (SFF-175/176).
**Cleaner option:** a fit-segment table written at finalisation, keyed by position (`pos_first`, `pos_last`, `t0_ns`, `period_ps`) (E/MG7C:10-11). It is evaluated as exact unlimited-size integers (E/T24G:29-33), covers every position (T24G:34), and is ignored in unfinished files (T24G:35-36).
- Gain: the key stays unique after a camera restart resets its frame number (MG7C:34-35). It also avoids a 2^53 overflow, since d × period_ps passes 2^53 after about 2.5 h at 30 fps (T24G:58).
- Cost: a new table in the sidecar layout.
- The fit itself is supported by evidence: arrival jitter is 4.6-4.8 ms SD, and the fit was within 0.56 ms of flash ground truth (E/FF01:33-35).

**4g. Drop the derived skellycam timing files for new takes.**
- Multiframe CSV: it holds the per-frame mean across cameras of `timestamp.from_recording_start.sec` (SCds create_multi_frame_csvs.py:44-45). Without it, freemocap computes the same mean of the camera timestamps (FMC:freemocap/core/reconstruction/recording_timing.py:42-47). The values agree by construction except for CSV text precision (DT8 narrowed to that).
- One certain change: the stored timing method moves from RECORDED to MEAN_CAMERA_TIMES (recording_timing.py:39-46). The label is written into the Parquet sources and read back (saved_observations.py:67-68).
- The addon reads the multiframe CSV only on its legacy_npy route (A73:utilities/recording_framerate.py:17-32). That route needs `output_data/*_3d_xyz.npy`, which no current code writes (FMC recording_status.py:113-135).
- `_stats.json` / `_stats.txt`: their only freemocap reader is the dead recording_framerate.py.

**4h. `.skat`**: v0 §7 (S:465-596): a timing record per callback (type 1), a packet record (type 2) and a drift table (type 3, provisional; SFF-260..263). `audio_latency_ns` is INT64_MIN until test A3 (SFF-251; E/5G42 item 3). If Opus is chosen, the timestamp means the host time of the first decoded sample, priming samples included (E/D9N1 item 6).

**4i. Live behaviour and unfinished takes**: v0 §10-§11. The header is written before the first frame (SFF-402). A crashed sidecar is read up to the first bad record CRC or partial record (SFF-450). A crashed file is read in place and reported unfinished, with a clean-end check (E/PV6S item 6).
- Proposed flow in freemocap (no code today): before probing videos, freemocap's status and playback paths read the `.skvt` header state from v0 §10-§11 (exact field not re-checked for this report) and report "needs repair" instead of calling `probe_video_files` on a killed MKV (today: FMC recording_status.py:170-190 counts by extension; playback_router.py:77,300 and mocap_router.py:167 probe). freemocap's UI shows the PV6S consent prompt and calls the skellyfileformat repair. Which UI owns the prompt (skellycam or freemocap) is open (Decision 24).

**4j. Take info file.** Proposed: skellycam writes `_info.json` at take start (via `.tmp` + rename) and again at the end. Today it is written only at finalisation (SCds recording_finalizer.py:55), so a crashed take has no `videos` or `camera_timing` map. FMC then falls back to filename labels and fps timing (recording_timing_reader.py:72-77; FMC video_group_helper.py:337-343). No v0 `.skellyrec.json` manifest (E/TDB5 item 2). Readers must still work from the sidecar headers alone (SFF-654/655).

---

## 5. 2D tracking sidecar

**Proposed: reuse `<rec>_data.parquet` for posthoc 2D, with take and camera links added.**
- OVERLAY_2D per camera: x and y in px plus visibility in [0,1], reference frame `camera:<id>:image` (FMC observation_inputs.py:212-225; FMC sample_encoding/observation_samples.py:98-109,129-130). BOXES_2D when a detector ran (observation_inputs.py:231-253).
- A missing point has x and y null and visibility 0.0 (observation_samples.py:134-139). Missing values are null, not NaN (channel_series.py:73; arrow_schema.py:108-115).
- Written first in posthoc as a 2D checkpoint (posthoc_mocap_task.py:120-138) and read back for restarts (saved_observations.py:40-114).
- Published atomically under a lock: temp file, fsync, replace (parquet_writer.py:28-91).
- Join to video frames by `frame_number`, which is the decode index = skellycam recording_frame_number (recording_timing.py:27-35) = `.skvt` write_index. No exact-ns key is needed. TFD Q8's log_time key existed for Lichtblick pairing (TFD:17).
- 2D rows use each camera's capture times (observation_publication.py:86-88,195-228). Test: camera a's 2D rows at [0.001, 0.04] s (FMC tests/test_posthoc_observation_recording.py:131-148).
- "Confidence" = the existing `visibility` channel. No new field.
- Raw vs filtered 2D: TFD Q9 wants both (TFD:32). Whether filtered 2D exists on dev-streaming is not verified.
- Saved observations require equal, consecutive frame numbers across cameras (saved_observations.py:62-65). See §8.
- Pixel origin and sub-pixel convention of OVERLAY_2D: **not verified**. TFD Q10 wants stored-JPEG pixel coordinates (TFD:33), and Q31 dealt with a 0.5 px centre shift (TFD:54). Desk test DT-K3.

**Links to the take and to each camera's sidecar (proposed change, so not "unchanged").**
- Today the Parquet's `recording_id` is the folder name (FMC observation_publication.py:245, `recording_id=structure.recording_name`), and camera ids are freemocap source labels in `camera:<id>:image` (observation_inputs.py:167-175), falling back to filenames (video_group_helper.py:337-343). Nothing in the Parquet names the `take_uuid` or a `camera_key`.
- TFD Q2 and Q12 asked for the same take_uuid (TFD:25, :35), and Q42 asks for matching by camera_key (TFD:62).
- Proposed rule: store take_uuid in the run or recording descriptor and, per camera, camera_key plus the `.skvt` file name (or segment_uid) in the source entry. The alternative is to state that the Parquet is linked by folder only and drop Q2/Q12's take_uuid requirement. Open (Decision 25). Test SFT-K2.

**Realtime 2D is not persisted today.** The only realtime file writer is the ChArUco pickle (FMC realtime/charuco_recorder_node.py:30,42,227). Skeleton output goes only to the websocket (websocket_server.py:42,118-182).
- **Default (reuse the writer):** at take end, publish the realtime 2D/3D as a Parquet run through the existing `ObservationRecordingRequest` → `publish_posthoc_observations` writer (FMC:freemocap/core/pipeline/dataflow/scientific_recording.py:207-224).
  - Caveat: the existing `CompletedScientificRecording.save` (scientific_recording.py:185-224) cannot take realtime output as it is. It needs a completed observation set, a matching result, a triangulation and per-source video metadata from `RecordingVideoSources` (scientific_recording.py:21,196-224). Its builders take `TrackedCameraFrame` events plus `RecordingVideoSources` and re-run triangulation in batch (scientific_recording.py:228-252,275-320). Only tests and a dataset tool call `save` (test_dataflow_scientific_recording.py:156,197,207,233; freemocap/tools/datasets/scientific_comparison.py:131).
  - So this option needs a new adapter from the realtime aggregator's output to `ObservationRecordingRequest`, or else it really means a posthoc re-run from the videos. Whether such an adapter works is not verified (DT10).
  - A crash loses realtime tracking, but posthoc can recompute it from video.
- **Cleaner option: a live CRC-framed journal** `<rec>.tracking.<ext>` (name proposed), folded into the Parquet as its own `run_id` after the take.
  - Evidence: `.skov` CRC records cost 29.3 µs and 3,283 B per frame for a 33-point skeleton plus 100 ChArUco corners, with coordinates stored as **float32** (scripts\overlays\overlay_model.py:288-293). JSONL cost 125.4 µs / 5,698 B. MessagePack wrote faster (23.7 µs) but was larger (6,890 B), storing float64 (overlays\FINDINGS.md:133,484).
  - All formats recovered every complete record over 28/28 clean cuts. Only CRC records rejected a 1-byte change, and MessagePack stopped at a 4 KiB zero hole (RES\overlays\bench\bench_overlay_cost_20261110T103707Z.json; verify_method_crash_modes.json; overlays\FINDINGS.md:484).
  - Record (proposed): type (2D raw / 2D filtered / 3D / parameter event), camera_key or group, tracker id, connection_frame_number, points, visibility. Points are float32 (matches the measured cost) or float64 (TFD Q26). The size and cost of float64 records are not measured (DT11). A header holds the take facts plus nodes/edges and source software (TFD Q37).
  - Frame link: connection_frame_number mapped through `.skvt` source_frame_number, with no skellycam IPC change. Alternative: put write_index or arrival time in shared memory (TFD Q20).
  - Cost: a new spec part, a writer in freemocap realtime, a fold step that must pass the arrow_schema validator (DT13), and a kill test (DT11). The synthetic data is a stand-in, not real trackers (overlays\FINDINGS.md "Real RTMPose 133-point output ... not sampled").
- Spec placement: E/W4PF item 8 says recorded overlay data from freemocap is "later work" (W4PF:21). A superseding entry is needed that defines "overlay" as burned-in drawings only and brings in tracking sidecars. Proposed: the format spec references the Parquet schema (FMC arrow_schema.py) and does not re-specify it.

---

## 6. 3D tracking sidecar

**Proposed: the same Parquet.** "2D sidecar" and "3D sidecar" are channel families in one file.
- RAW_KEYPOINTS_3D (stage TRIANGULATION) and KEYPOINTS_3D (gap-filled, filtered, aligned; stage FILTERING). Units mm, reference `calibrated_world`, basis `blender_x_right_y_forward_z_up`. With one camera, `camera_plane` in px (FMC spatial_points.py:24-31,48-75,85-101; posthoc_mocap_task.py:242-246,263,284-285).
- Skeleton per model: MAPPED_KEYPOINTS_3D, LANDMARKS_3D, SEGMENT_ORIGINS, ROTATIONS_WORLD/LOCAL (wxyz), JOINT_ANGLES (rad), RIGID_BODY_RESIDUALS (reconstruction_samples.py:166-259).
- DERIVED_POINTS `center_of_mass` and `xcom` (reconstruction_samples.py:243-301; derived_point_name.py:7-8). There is no per-segment CoM channel (derived_point_name.py). TFD/HO Q44 asked for segment CoMs (HO:50). Add them only if Dom confirms.
- Reprojection error, coverage and weights per camera (diagnostic_samples.py:16-51). The filter report goes in run.processing (observation_publication.py:163-166).
- Static scale fit is stored in the descriptor (fit_channels.py:18-57). Camera geometry is frozen per run (recording_descriptor.py:101-103).
- All 3D rows sit on the synchronized timeline (observation_publication.py:119-128,175-191). In the test above, 3D rows are at [0.0015, 0.0405] s (test_posthoc_observation_recording.py:131-148). 3D points link to frames only through time and frame_number (TFD Q19 at TFD:42).
- The Blender addon already consumes this file (A73:freemocap_data_handler/parquet_recording.py:14-21).

Why not split 2D and 3D into separate files: the addon reads exactly one `*_data.parquet` (parquet_recording.py:16-20), the validator checks grids across channels (arrow_schema.py:233-258), and the exports read the one file (wide_csv.py, tall_csv.py). Splitting would change all three. The option is kept for Dom (Decision 11).

Known issues to note, not fix now:
- Size: 222 frames gave 1,940,280 rows and 1,108 frames gave 9,683,920 rows, about 8.7k rows per frame (FMC recording-folder-contract.md:199-200; a doc figure, not measured in code). No measured problem was found, so no layout change is proposed.
- Inference, not verified: NPY/NPZ export requires every selected array to share frames and timestamps to within 4 ULPs (wide_csv.py:144-147,200-206). Exporting OVERLAY_2D together with 3D should then fail when capture and synchronized times differ (DT12).
- Whether int64 arrival_ns survives float64 `timestamp_s` exactly is not verified (DT14). It does not matter for a frame_number join.

**Cleaner option (skeleton edges):** `tracker_schema.json` is read by playback (playback_router.py:707-736,839-845) but never written (git grep; FMC tests/test_recording_store.py:422 asserts publication does not write it). No edges were found in recording_model.py (grep). Proposed: add NWB-style nodes and edges (TFD Q37 at TFD:60) to RecordedModel (recording_model.py:15-27), then move the playback read there. Cost: recording_model.py, playback_router.py, a schema version bump (recording_descriptor.py:191-196) and the frontend (not checked).

---

## 7. Calibration, tracker schema, recording info, ChArUco

**Calibration TOML: keep.** It is the authority (FMC RECORDING_CONTRACT.md:67), written as `<rec>_camera_calibration.toml` (calibration_paths.py:18-20; calibration_save.py:21-51).
- Cleaner, cheap: make the declared name match (recording_structure.py:88-132 says `<rec>_calibration.toml`).
- Cleaner: the addon takes the last `*.toml` from os.listdir (A73:core_functions/add_capture_cameras/add_capture_cameras.py:66-68). FMC's `find_recording_calibration` prefers the exact name and raises on several matches (calibration_paths.py:28-39). Use FMC's rule in the addon.
- If pixels stay in sensor orientation (§9 option b), new calibrations are in stored-pixel space and old rotated ones need converting (TFD Q46 at HO:52). The conversion is not verified.
- TOML translation units are probably mm (the addon divides world_position by 1000, A73 parquet_scene.py:210). Not verified in TOML code.

**Recording info.** Today skellycam writes `<rec>_info.json` (SCds recording_info.py:68-70,80-104) and freemocap writes `<rec>_recording_info.json` (FMC:freemocap/core/recording/recording_info.py:9-47). skellycam's reader globs `*_info.json` (SCds recording_metadata.py:16) and raises when two files disagree on a field (:26-27). The glob matches both files.
- **Default (reuse-first):** keep both. skellycam reads the exact name `{rec}_info.json`, writes it at start and end (§4j), and the `videos` / `camera_timing` maps point at `.mkv` / `.skvt`. These maps are the seams FMC uses (video_associations.py:12-48; recording_timing_reader.py:18-31).
- **Cleaner option:** one file. skellycam writes `<rec>_recording_info.json` directly, and freemocap merges its "processed" block into it. freemocap already reads the canonical name first (recording_info.py:11-16). Cost: the filename in SCds recording_info.py:68-70, plus the readers' glob. This removes the clash for good.
- Note: SCdr (dom/research) does not write the `videos` / `camera_timing` / `multiframe_timing` fields (`git diff` of recording_info.py removes lines 86-97). The new writer must write them.

**`charuco_observations_realtime.pkl`**: a pickle of observations keyed by connection_frame_number (charuco_recorder_node.py:30-31,158-159,183-231). Posthoc maps it to recording frames through the camera CSV (video_node.py:350-397,491-509). The contract calls it a disposable cache (RECORDING_CONTRACT.md:55-58). Whether the node is actually created is not verified: realtime_pipeline.py:255 initialises it to None.
- **Default:** keep the pickle as a cache, and switch its frame mapping from CSV columns to `.skvt` source_frame_number. That write_index = connection_frame_number − first_recording_frame_number is inferred from the shared recording window (SCds camera_orchestrator.py:102-116; camera_group.py:200-201,239-240), not verified (DT11b).
- **Cleaner option:** replace it with ChArUco tracker records in the live journal or a Parquet run (TFD Q45 at HO:51). Cost: charuco_recorder_node.py and the video_node.py reader. Keep pickle reading for old takes.
- If pixels become sensor-orientation, the cache (rotated coordinates, camera_node.py:292-295) is reused for unrotated posthoc frames by frame number (video_node.py:379-385). The coordinates would disagree. This is not an issue under rotation option (a) (§9).

**`charuco_3d_xyz.npy`**: written only on the Anipose path with ground-plane alignment (anipose_calibration_helpers.py:138-146). No reader found (git grep). Default: leave it. Cleaner: stop writing it.

**`charuco_board_info.json`**: used only by dataset tools (FMC tools/datasets/preparation.py:371; inspection.py:92-97). Leave it.

**Dead code** (clean-up with no format effect; cleaner option):
- recording_framerate.py (no callers).
- extract_camera_id_from_video_path.py: imports a non-existent `posthoc_pipelines` module (FMC utilities/extract_camera_id_from_video_path.py:3), and its regex does not match skellycam names.
- get_video_paths.py and get_number_of_frames_of_videos_in_a_folder.py (no callers; FMC utilities/get_video_paths.py:8-9).
- `create_camera_frame_csv_row_recarray` (SCds create_camera_csvs.py:110-178): no callers, and it uses pre+pre instead of pre+post (line 128).
- update_1_4_path_names.py (no callers).
- **Do not delete** the addon's legacy_npy route: it serves old recordings (D19).

---

## 8. The frame grid

Who needs equal counts and frame i = data row i:
- posthoc (FMC video_group_helper.py:322-333); video_sources.py:46-56; playback (playback_router.py:303-305,784-787); import (mocap_router.py:170-178); the frontend (freemocap-ui usePlaybackController.ts:54); saved observations, which also need consecutive frames (saved_observations.py:62-65).
- Blender maps video frame i to data frame i and never reads the movie fps, PTS or duration. Planes use frame_start=0 (A73 parquet_scene.py:186-192). The scene frame range is the Parquet frame_number range (A73 parquet_import.py:203). The test checks `image_user.frame_duration >= len(frames)` (A73 tests/blender_complete_scene_checks.py:158).

The v0 gap: index PTS uses write_index, so a camera that drops frames would hold fewer blocks (GF02 gap60 had 831 and drop50 874, against 891). v0 has no fill rule (a search of S for fill/duplicate finds only S:393, 666, 1013, which are unrelated).

**What lockstep does today (from code and measurement):**
- A camera may grab only when its frame count is ≤ every other camera's count (SCds camera_orchestrator.py:118-131, `should_grab_by_id` → `_all_camera_counts_greater_than_or_equal_to_camera`). The group therefore paces to the slowest camera. The faster cameras lose frames at the gate, before the writer, and the code shown duplicates nothing.
- Measured: the generic camera delivers about 25.7 fps when 30 is requested, so lockstep paces the whole group to it, and the gate dropped 14% of the C930e's frames beside it (PLAN:349; docs\vlc_playback_rate_20261112.md:30).
- Every camera records the same frame-number window (SCds camera_orchestrator.py:102-116; camera_group.py:200-201,239-240). The finalizer refuses unequal counts (SCds recording_finalizer.py:166-170). recording_frame_number = arange(n) (create_camera_csvs.py:54). The folder README states equal counts (recording_finalizer.py:24-31).
- Consequence (inferred from the gate code and the measured rate, not verified on a real take): under lockstep, index PTS at the requested rate is wrong by the delivered-rate ratio for every camera in the group, for the whole take. With the generic camera that is about 14% short.
- Still not verified: what happens when a grab or retrieve fails or times out under lockstep (DT7, narrowed to that).
- The plan removes lockstep in phase 2 (PLAN:397, row 2.2: "removing the gate", with per-camera `frame_status` fresh/repeated/missing). Once the gate goes, a fill rule is required.

**Proposed default (reuse-first): keep skellycam's lockstep grid now.** write_index = recording frame number, the same N on every camera.

**The spec still states a rule** for a grid position with no new frame, because plan row 2.2 will need it and the spec cannot depend on lockstep:
- Proposed rule: the writer repeats the previous JPEG bytes and sets the new **`filled`** flag (§4e, reserved bit 3). This is a change to v0. v0's `repeat` keeps its meaning (camera re-delivered a frame number; S:362; SFF-170).
- Open: what source_frame_number and arrival_ns hold on a filled record (copy of the previous, or INT64_MIN for arrival). Also how SFF-170 sets `gap` on the next real frame after a fill.
- The filled record must still yield a strictly increasing time for RecordingTiming (recording_timing_reader.py:105-112), for example the fit time.
- How OpenCV, PyAV and Blender treat repeated blocks is untested (DT4).
- freemocap side: no FMC code reads such a flag (it is new). Posthoc would otherwise track, triangulate and filter the copies as real observations. Proposed: freemocap reads `filled` from the `.skvt` and writes null 2D for those positions, reusing the missing-point convention (x, y null, visibility 0; observation_samples.py:134-139). The alternative is to treat the copies as real. Open (Decision 26). Effect on 3D and the filter: DT4b.

Rejected alternative: freemocap resamples onto a grid after the take. That means more code and a decode, with no evidence.

**Uniform rate:**
- The container is constant-rate by construction (SFF-104). VLC played 300 frames at 30 fps in 10.03-10.09 s (docs\vlc_playback_rate_20261112.md:13).
- freemocap's analysis rate comes from timestamps (posthoc_filtering.py:50-56). Blender's scene fps = 1/median(diff(times)) (A73 parquet_import.py:204-207).
- A take with drops plays shorter than the event in an external player (RES\sidecar_embedding\FINDINGS.md:36). Inferred from measured rates: the generic camera 14% short, Kiyo Pro 2.1% short, C930e 0.17% long (vlc_playback_rate_20261112.md:21-28).
- How Blender maps a movie whose fps differs from the scene fps is not verified (DT-B2).

---

## 9. Rotation, old recordings, imports, Blender, browser, Lichtblick, skellysync

### Rotation
Today skellycam bakes rotation into the pixels (SCds video_recorder.py:52-55,96-100). The default is no rotation (SCds camera_config.py:27), so only cameras the user rotates are affected. Every reader assumes upright pixels:
- posthoc reads rotation only from the container (SCds sequential_video_reader.py:49-53);
- browser_stream raises on any rotation (SCds browser_stream.py:69-70);
- the addon has no rotation handling (A73 grep of load_videos, add_capture_cameras, parquet_scene) and uses max(w, h) for focal length (add_capture_cameras.py:176-179);
- the Parquet image reference has no rotation field (observation_inputs.py:167-175).

**Option (a), reuse-first: lossless rotation at write time (tj3Transform), with display_rotation = 0.**
- Evidence: libjpeg-turbo 3.2.1 tj3Transform was DCT-exact in 228/228 frame × rotation cases. All 33 generic_1080p cases returned TJERR_WARNING (-1) while still DCT-exact, so the writer must accept warning outputs (RES\jpeg_passthrough\FINDINGS.md:379-383, 655). For 4:2:0 or odd-size cameras, add TJXOPT_PERFECT or TRIM (FINDINGS.md:656, inferred).
- Cost: 2.0-2.2 ms/frame at 720p and 6.8-8.9 ms at 1080p, only for rotated cameras (EI:59; jpeg_passthrough FINDINGS.md:654).
- Readers need no rotation logic. But rot90/270 output is 4:4:0 chroma (FINDINGS.md:382), and the only decode evidence for 4:4:0 is from browsers (FINDINGS.md:370). Decoding 4:4:0 MJPEG in MKV with FFmpeg/OpenCV/PyAV/Blender is not verified (DT-B4, DT9).
- It overrides v0 SFF-102 (bytes unchanged) and SFF-103 (sensor orientation, S:156-158), and the accepted E/68Z6 ("The writer does not rotate the pixels", 68Z6:7-8). Those need superseding. Note that the user asked to go back to v0, and v0's own rule is option (b).
- Throughput at 16 × 1080p60 with rotated cameras is not verified (DT9).

**Option (b), v0's rule: sensor-orientation pixels, display_rotation in the `.skvt`** (SFF-103/159; E/68Z6).
- Gain: byte-identical passthrough, and one pixel space for 2D and calibration (TFD Q10 at TFD:33). The jpeg_passthrough findings name this as the way to take rotation cost off the record path (FINDINGS.md:657, inferred, untested).
- Cost: apply rotation in SequentialVideoReader, video_node and annotation_workers (cv2), browser_stream and the addon. Add a rotation field to the Parquet image reference. Convert calibrations. Fix the ChArUco cache (§7).
- Shape hazard: cv2 metadata against the PyAV frame shape check (video_sources.py:166-168).
- Whether Blender can rotate a plane or texture from metadata is not verified (DT-B4).

**Never use a container rotation flag.** VLC 3.0.24 rotated no MKV. OpenCV auto-orients, and its ORIENTATION_META uses the opposite sign. PyAV only reports `frame.rotation` (RES\rotation_flag\FINDINGS.md §0, §3). browser_stream refuses it.

Also: a reader ignores a JPEG EXIF orientation tag (E/T24G item 12), because browser decoders apply EXIF by default (T24G:59).

### Old recordings (D19 / E/X1G6)
Keep every existing reader: MP4 discovery by extension, RecordingTiming's CSV branch, `_info.json`, the pickle and the addon legacy_npy route. New readers are chosen when a `.skvt` is present. New takes write only MKV, MKA, `.skvt`, `.skat` and the Parquet (plus the journal, if chosen).

### Imported and skellysync-synchronized videos (new)
- freemocap's import copies videos into `synchronized_videos/` with VideoCopyPlan (FMC mocap_router.py:337-366). After a skelly_synchronize run, each destination is named `<src.stem>.mp4` whatever its contents (mocap_router.py:357). Without sync, the original names are kept (mocap_router.py:359-360). skelly_synchronize is pinned to the moving branch `philip/rewrite` (FMC pyproject.toml:54).
- Whether imports produce `_info.json` or timing files was not checked.
- Proposed: imported and synchronized foreign videos stay legacy-read inputs (they are not skellycam captures, so D19's "write only the new format" applies to skellycam/skellysync capture, not to user files). The alternative is to convert them to MKV + `.skvt` at import. Open (Decision 27).

### Blender
- Minimal patch (default): accept `.mkv` at A73 parquet_scene.py:161 and :165, and in the addon's tools/reference_data.py:55 so the test snapshot copier keeps MKVs. The legacy-route sites (load_videos.py:12-13; add_capture_cameras.py:142) serve old MP4 takes and need no change.
- Cleaner: one shared VIDEO_SUFFIXES helper, matched case-insensitively and sorted. Sort in load_videos, which uses set() today (:15). Pair cameras by id, not list position (add_capture_cameras.py:196-201), and fail on duplicates.
- Camera backgrounds load `synchronized_videos/<Path(camera['id']).name>` and skip silently if absent (A73 parquet_scene.py:203-229). Whether CameraModel.id (FMC camera_model.py:18) equals the video filename is not verified.
- Pin the addon to an exact rev. FMC pins a moving branch (FMC:pyproject.toml:53), against the pin-exactly rule.
- Test against 73e1b3e, not the installed main build, which has no Parquet route.
- The addon prefers annotated MP4s when present (A73 parquet_scene.py:160-161; load_videos.py:297-303). The scene test counts video planes against annotated_videos media in the reference (A73 tests/blender_complete_scene_checks.py:151). A test on a take with an `annotated_videos/` folder can therefore pass without loading any MKV (see DT-B3).
- Automatic Blender packaging in freemocap supports Windows x64 only (FMC freemocap/core/blender/local_package.py:35-36). Known limit; the Blender route is untested off Windows.
- **Gating unknown:** whether Blender (5.2; FMC tests use blender='5.2', FMC tests/test_blender_preparation.py:61) decodes MJPEG MKV through `images.load` / `movieclips.load` with frame_duration = N. Not verified (DT-B1). If it fails, the fallback is a freemocap export step that writes MP4 (or a byte-copied MJPEG container Blender accepts) for Blender. Cost: a second copy of the video for each take sent to Blender.

### Browser
- FMC's raw route already maps `.mkv` to `video/x-matroska` (playback_router.py:580-587). `/browser` re-encodes with PyAV through browser_stream, which needs exactly one video track, `time_base` and `average_rate` (browser_stream.py:51-55). Whether PyAV sets average_rate for an index-PTS MJPEG MKV is not verified (DT3).
- The frontend maps frame to time as totalFrames / nominal_fps (usePlaybackController.ts:39-41; browser-video.ts:78-84). This matches SFF-104.
- MJPEG does not play in `<video>`, MSE or WebCodecs in any container (EI:64). The longer-term path is JPEG by byte Range plus ImageDecoder: 450/450 fetches (EI:56). Capture-time sync from the sidecar gave 0 mismatches in 48/48 cells (RES\chromium_sync_scrub\gapfill\GF08_ts_sync.json).

### Lichtblick
Lost for the take folder. No test opened an MKV in Lichtblick (grep rc=1). tracking_sync tested MCAP only (RES\tracking_sync\summary_gpu.json, summary_swiftshader.json). Proposed: drop it, which reverts D29. An optional MCAP export for review is possible but not verified.

### skellysync
v0 §8 puts a FLAC track inside the camera MKV (SFF-300). That breaks "MKV holds only video".
- FLAC kept the OpenCV count correct in 20/20 at 30, 60 and 120 fps (RES\audio_skellysync\FINDINGS.md:96-104).
- Untrimmed Opus made the count one high at 120 fps in 20/20, fixed by dropping the 312 pre-skip samples. Vorbis gave 451 for 450 (audio_skellysync\FINDINGS.md:18, 69, 101-103).
- FLAC in the camera MKV broke live offsets, 0/1,799 (audio_offsets.json S4; SFF-403).
- Proposed: a separate `.mka` for skellysync too. This also gives review-3 B7 an operational definition: a camera file has one V_MJPEG track, and an audio file has one audio track.

---

## 10. v0 problems: removed and remaining

Every review-3 item is a reviewer claim and was never verified against the files (R3:3).

**Removed by never embedding:** SFF-105/106; SFF-352..363; finalisation steps 5-6; `separate_final`; crash rows S:741-743; golden files G2, G10, G11 and the embed parts of G1, G12, G13; review-3 B1, B3, B4, the step-6/SFF-363 major, the separate_final major, the appender minors, and F1.

**Removed by porting accepted entries:**
- B5/B6: reader states, reasons, warnings and JSON (E/WG08:12-50), plus RFC 8785 (E/5G42 item 4). WG08's MCAP reasons (`bad_schema`, `bad_chunking`, `crc_mismatch`) and `torn_bytes` need sidecar equivalents. v0 had `bad_magic`, `bad_header_crc`, `bad_record_size` and `out_of_bounds` (SFF-179).
- The stale-manifest and multi-take items (R3:28-30) and F2, by E/TDB5 items 2-3 (no manifest).
- F4, answered by E/WG08.
- F6 and the SFF-104 u64 overflow item (R3:31, R3:58): answered by E/752H item 7 (752H:30-31) and the arithmetic in §2.

**Removed by other proposals:** the §8 audio-in-MKV rules. SFF-402/403 live offsets, if Decision 8 picks finalise-time offsets. B2's audio deletes and SFF-204/208, only if Opus straight to MKA is chosen.

**Remaining:**
- B2: audio step-7 delete order (if FLAC).
- B7: answered by the separate-file rule above (proposed).
- B8 / F3: latency sign in SFF-261 (provisional; R3:55).
- F5: state for a `.flac` whose take has a finalised `.mka` (R3:57). It returns only if Decision 5a (FLAC) is chosen.
- The step-2 failure loop inside recovery (R3:23).
- Drift record size, json_size with no JSON, table contiguity (R3:24).
- SFT-057, SFT-550, SFT-660 test items (R3:25-27).
- needs_recovery counting (R3:30).
- camera_key exactness in JS (R3:32).
- avio_flush and "flush to file" vs "flush to disk" (R3:33).
- Windows FILE_SHARE_DELETE blocking the recovery rename (R3:34).
- adc_ns sentinels (R3:35).
- SFF-503 vs crash row 2, if recovery still writes `<media>.tmp` (R3:21).
- FMC/5K7G "player draws the frame label from the sidecar" not stated in the spec (R3:42).
- **New:** the "strictly increasing" timing rule (§4c), the `filled` flag and grid fill rule (§8), the tracking sidecar part with take/camera links (W4PF item 8 supersede; §5), and non-MJPEG capture (§2a).

---

## Existing file → keep / change / replace

| File (today) | Writer | Proposed for new takes | Evidence |
|---|---|---|---|
| `synchronized_videos/<rec>.id-<cam>.idx-<i>.mp4` (X264 via cv2.VideoWriter; PyAV fallback with index PTS) | skellycam | **Replace** with `.mkv` (MJPEG, index PTS); same name pattern | SCds video_filename.py:7; camera_config.py:29; video_recorder.py:120-134; pyav_video_writer.py:14,33; EI:53-54 |
| `synchronized_videos/timestamps/camera_timestamps/<rec>.camera<id>.timestamps.csv` | skellycam at finalisation | **Replace** with `.skvt`; CSV reader kept for old takes | recording_timing_reader.py:13-15,80-117; recording_finalizer.py:53-61; sidecar_durability.md |
| `synchronized_videos/timestamps/<rec>_timestamps.csv` (multiframe) | skellycam | **Drop**; FMC computes the same mean as MEAN_CAMERA_TIMES (label changes) | create_multi_frame_csvs.py:44-45; FMC recording_timing.py:36-47 |
| `<rec>_stats.json` / `_stats.txt` | skellycam | **Drop**; the only reader is dead code | recording_info.py:72-78; recording_framerate.py (no callers) |
| `<rec>.audio.wav` + `audio_timestamps.json` | skellycam | **Replace** with `.mka` + `.skat` | audio_recorder.py:121-162; no FMC reader (mocap_router.py:141,237) |
| `synchronized_videos_README.md` | skellycam | **Keep** (update text) | recording_finalizer.py:24-31,69-71 |
| `<rec>_info.json` | skellycam at finalisation | **Change**: write at start and end, exact-name read, maps point at `.mkv`/`.skvt`. Cleaner: merge into `_recording_info.json` | recording_finalizer.py:55; recording_info.py:86-97; recording_metadata.py:16,26-27 |
| `<rec>_recording_info.json` | freemocap | **Keep** | FMC recording_info.py:9-47 |
| `<rec>_data.parquet` | freemocap posthoc | **Keep** as the 2D+3D tracking sidecar; **add** take_uuid and camera_key links (Decision 25); cleaner: add edges to RecordedModel | arrow_schema.py:15-29; parquet_writer.py:28-91; observation_publication.py:245; A73 parquet_recording.py |
| `<rec>_camera_calibration.toml` | freemocap | **Keep**; fix the declared name | calibration_paths.py:18-20; recording_structure.py:88-132 |
| `output_data/charuco_observations_realtime.pkl` | freemocap realtime | **Keep** as a cache, map via `.skvt`; cleaner: replace with journal/Parquet run | video_node.py:350-397,491-509; RECORDING_CONTRACT.md:55-58 |
| `output_data/charuco_3d_xyz.npy` | freemocap (Anipose) | **Keep**; cleaner: stop writing (no reader) | anipose_calibration_helpers.py:138-146 |
| `tracker_schema.json` | none (read only) | Cleaner: retire, read RecordedModel | playback_router.py:707-736; test_recording_store.py:422 |
| `annotated_videos/*.annotated.mp4` | freemocap posthoc | **Keep** as derived output, never in the take format (Decision 14) | annotation_output.py:36-41,58-65 |
| `exports/**`, `<rec>.blend` | freemocap | **Keep** (derived) | wide_csv.py:161-166; export_to_blender.py:44-45 |
| (none) | — | **New**: `.skvt`, `.skat`, `.mka`; optional live tracking journal | S §5, §7; overlays bench |

## skellycam code to replace or keep for legacy reading (new)

| Code (SCds) | What it does today | Proposed |
|---|---|---|
| video_recorder.py:52-55,96-100,120-134 | rotates pixels; picks cv2.VideoWriter or PyavVideoWriter | **Replace** with the MJPEG MKV writer (skellyfileformat[write]) |
| recording_finalizer.py:147-171 | cv2 count/shape validation against camera_config image_shape (camera_config.py:156-164) | **Replace**: validate from `.skvt` records and MKV blocks |
| fourcc_codec_helpers.py:71-76 | maps MJPG → `.avi` | **Keep** for legacy only; the new writer always writes `.mkv` |
| process_and_save_recording_timestamps.py:37-48; create_camera_csvs.py; create_multi_frame_csvs.py | write timestamp CSVs at finalisation | **Retire** for new takes; the CSV *reader* stays |
| audio_recorder.py:121-162 | WAV + JSON | **Replace** with FLAC/Opus → MKA + `.skat` |
| camera_config.py:29 `DEFAULT_WRITER_FOURCC = "X264"` | writer default | **Remove** for new takes (§2a) |
| recording_timing_reader.py | CSV reader | **Keep**, add `.skvt` dispatch (§4c) |

## Existing freemocap tests, fixtures and tools to change (new)

| Site (FMC) | Assumes | Proposed |
|---|---|---|
| freemocap/tests/pipelines/mocks/mock_camera_group.py:73-75 | globs `*.mp4`, raises "No .mp4 videos found" | parametrise over `.mp4`/`.mkv` |
| freemocap/tests/reference_recordings/test_fresh_posthoc.py:37-41 | `*.mp4` sources, `<name>.annotated.mp4` | keep for legacy; add a new-format variant |
| freemocap/tools/datasets/catalog.py:41; inspection.py:80 | accept only `.mp4` | accept `.mkv` too |
| 34 files under freemocap/tests matching `timestamps.csv`, `_info.json`, `.mp4` or `camera_timestamps` (`git grep -l` count) | MP4 + CSV takes | per file: keep for legacy, or parametrise; per-file review not done |
| Reference data (`poe datasets export test_data` / `sample_data`) | old format (D19) | add one new-format reference take (MKV + `.skvt` + Parquet); see DT-K4 |

---

## Decisions for Dom

Accepted (Dom, 2026-11-13): decisions 1, 2, 3, 4 and 5, as marked below. The rest are proposed, recommendation first. DT-B1 has been run since: see decision 15.

1. **"Timestamps" in the MKV/MKA.** (a) Container PTS only, sidecars always separate. (b) Embed the timing sidecar at finalisation (v0 §9). **Recommend (a)** (R3:9-12; E/SFK5:42-44). **Accepted (Dom, 2026-11-13): (a).**
2. **Timing sidecar format.** (a) v0 `.skvt`/`.skat` binary. (b) Live CSV flushed per row. (c) Parquet. Kill survival is equal for (a) and (b) (sidecar_durability.md); (c) is not appendable live (parquet_writer.py:69-90). **Recommend (a)**, for D19 policy, per-record CRC (measured on overlay formats only) and fixed-size records. (b) would keep the existing reader. **Accepted (Dom, 2026-11-13): (a).**
3. **Keep writing the legacy CSVs too?** (a) No, per D19; freemocap reads `.skvt` through RecordingTiming. (b) Also write CSVs at finalisation. **Recommend (a).** **Accepted (Dom, 2026-11-13): (a).**
4. **Rotation.** (a) Lossless rotate at write, display_rotation 0 (supersedes 68Z6, SFF-102/103). (b) v0's rule: sensor orientation + display_rotation in `.skvt`, with reader patches. (c) Re-encode as today. **Recommend (a)** for reuse, pending DT-B4 and DT9 (4:4:0 decode not verified). (b) is what v0 says and the cleaner option. **Accepted (Dom, 2026-11-13): (b), store sensor orientation** (v0 SFF-102/103 and E/68Z6 stand; DT9 and the 4:4:0 question no longer apply; the Blender addon must rotate the plane from `display_rotation`, DT-B4).
5. **Audio codec.** (a) FLAC (`frame_size=1024`) → MKA (v0; supersedes D9N1). (b) Opus straight into MKA with `cluster_time_limit=100` (keeps D9N1). **Recommend (a)** for crash loss (0 vs about 122 ms per kill); (b) is the cleaner option, pending DT-A1. **Accepted (Dom, 2026-11-13): (a) FLAC.**
6. **skellysync audio.** (a) Separate `.mka`. (b) Inside the camera MKV (v0 §8). **Recommend (a).**
7. **Fit storage.** (a) v0 per-record `fitted_ns`. (b) MG7C position-keyed segments with T24G integer evaluation. **Recommend (a)** for reuse; (b) is the cleaner option.
8. **Byte offsets.** (a) Filled at finalisation by scan. (b) Live, SFF-402, with `cluster_size_limit=1`. **Recommend (a)**; (b) if live byte-range reading of crashed files is wanted (needs DT5).
9. **Manifest.** (a) None; headers hold the take facts, `_info.json` written at start and end. (b) v0 `.skellyrec.json`. **Recommend (a)** (E/TDB5).
10. **Folder.** (a) Keep `synchronized_videos/`, fix the declarations. (b) Move to `videos/synchronized/`. **Recommend (a).**
11. **Tracking files.** (a) One Parquet with 2D and 3D channel families. (b) Separate 2D and 3D files. **Recommend (a).**
12. **Realtime tracking persistence.** (a) Publish a Parquet run at take end through the existing writer, via a new realtime adapter (not verified, DT10). (b) Live CRC-framed journal, folded into the Parquet later. **Recommend (a)** for phase 2; (b) is the cleaner option if realtime results must survive a crash.
13. **Live-tracking frame key** (only if 12b). (a) connection_frame_number mapped through `.skvt`. (b) write_index or arrival time in shared memory (TFD Q20). **Recommend (a).**
14. **Burned-in overlays.** "No burned-in overlays" covers the take format only; freemocap's `annotated_videos/` stays as derived output. Alternative: stop writing them, though the addon prefers them (A73 parquet_scene.py:160-161). **Recommend keep as derived.**
15. **Blender route.** (a) The addon reads `.mkv` after the suffix patch. (b) freemocap exports a Blender video. **Recommend (a) if DT-B1 passes, else (b).** DT-B1 ran on 2026-11-13 and passed for index PTS (frame counts exact in all three loaders, 20/20 frames identical) and failed for real PTS (`recording_upgrade/results/blender_mkv/FINDINGS.md`). So the recommendation is (a), still pending DT-B3 (the addon itself on an `.mkv` take).
16. **Which `.skvt` time RecordingTiming returns.** (a) Player time (SFF-176), relative to take_start_host_ns. (b) Arrival time. **Recommend (a).** The spec must also require strictly increasing times (§4c).
17. **Grid.** (a) Keep skellycam lockstep now; spec a fill rule with a new `filled` flag for when the gate goes (PLAN:397). (b) Empty or placeholder block. (c) freemocap resamples. **Recommend (a)**, pending DT7 and DT4.
18. **Recording info files.** (a) Keep both, exact-name read. (b) One merged `<rec>_recording_info.json`. **Recommend (a)** for reuse; (b) is the cleaner option.
19. **ChArUco pickle.** (a) Keep as a cache, map via `.skvt`. (b) Replace with tracker records. **Recommend (a).**
20. **Lichtblick.** Drop it (reverts D29). **VLC:** nice to have, not required. With FLAC, VLC played an `.mka` complete (vlc_check.json, tested with an embedded sidecar).
21. **Naming drift.** Use `.skat` (v0 §7, S:465), not `.skau` (D23, PLAN:456).
22. **Exact pins.** Pin every git and range dependency exactly: freemocap_blender_addon, skellycam, skellytracker, skellyforge (FMC pyproject.toml:50-53), skelly_synchronize (:54, branch philip/rewrite), skellylogs and skellypings (:56-57, no rev), pyarrow (`>=25.0.1`, :8), opencv-contrib-python (unpinned, :17; skellycam `==4.12.*`, SCds pyproject.toml:55) and av (skellycam `>=18.1.0`, :68). Choose one av version and run DT1 with it. Add skellyfileformat as an exactly pinned dependency of skellycam (writer) and freemocap (reader). **Recommend all.**
23. **Non-MJPEG capture** (§2a). (a) Encode YUYV to JPEG (v0 SFF-102), refuse H264 capture. (b) Refuse all non-MJPEG capture for new takes. **Recommend (a)**, pending DT-E1.
24. **Who handles an unfinished take** (§4i). (a) freemocap's status check reads the `.skvt` state, shows the PV6S prompt and calls skellyfileformat repair. (b) skellycam's UI only. **Recommend (a)** for freemocap takes.
25. **Parquet link to the take** (§5). (a) Store take_uuid and per-camera camera_key + `.skvt` name in the Parquet descriptor. (b) Link by folder only; drop TFD Q2/Q12's take_uuid requirement. **Recommend (a).**
26. **Filled positions in freemocap** (§8). (a) freemocap writes null 2D for `filled` positions. (b) Treat copies as real frames. **Recommend (a)**, pending DT4b.
27. **Imported and synchronized videos** (§9). (a) Stay legacy-read inputs. (b) Convert to MKV + `.skvt` at import. **Recommend (a).**
28. **Review-3 F3** (latency sign, R3:55): carry as provisional until test A3. **F5** (R3:57): decide only if 5a is chosen.

---

## Test list

### Disposition of v0's existing conformance suite (C, 108 SFT IDs)
Count from `git show bd62b60:spec/conformance.md | grep -oE 'SFT-[0-9]+' | sort -u | wc -l` = 108. Section level only; a per-test mapping was not done for this report.

| C section (line) | Proposed disposition |
|---|---|
| Conventions §2 (C:25) | keep |
| Versioning §3 (C:51) | keep; add 7K3C meanings |
| Video MKV profile §4 (C:101) | keep, minus SeekHead/no-Attachments tests (SFF-105/106) |
| Video timing sidecar §5 (C:166) | keep; change for camera_key MUST, `filled` flag, strictly increasing, no legacy_ns |
| Audio FLAC in `.mka` §6 (C:305) | keep if 5a; replace with Opus tests if 5b |
| Audio timing sidecar §7 (C:353) | keep |
| Audio in the camera MKV §8 (C:404) | drop (Decision 6a) |
| Embedding and finalisation §9 (C:420) | drop embed tests; keep any finalisation-order tests for the separate sidecar |
| Segment UID, live and final offsets §10 (C:517) | keep; live-offset tests only if 8b |
| Unfinalised and crashed files §11 (C:540) | keep; add PV6S consent and 5G42 marker |
| Names §12 (C:589) | keep; check `.skat` naming |
| Files not in this format §13 (C:620) | keep |
| skellysync camera sidecar §14 (C:629) | change: separate `.mka` |
| The recording as a whole §15 (C:650) | change: no manifest (TDB5), take_uuid grouping |

### New conformance tests (proposed IDs; only where v0 has no test)
| ID | What it checks |
|---|---|
| SFT-N1 | Camera MKV has no audio track and no rotation element |
| SFT-N2 | `.skvt` player time strictly increasing |
| SFT-N3 | `filled` flag set exactly on writer-filled positions; `repeat` keeps its v0 meaning |
| SFT-N4 | Folder grouping by take_uuid without any manifest; extra files reported |
| SFT-N5 | Reader result JSON (WG08 states, reasons, warnings; RFC 8785) on golden takes |
| SFT-X1 | Legacy MP4+CSV take is recognised as legacy and read by the old readers |
| SFT-K1 | Tracking Parquet frame_number joins to `.skvt` write_index for every camera |
| SFT-K2 | Parquet camera ids resolve to exactly one `.skvt` by camera_key; take_uuid matches |

### Desk tests for unverified items
| ID | Test | Gates |
|---|---|---|
| DT-B1 | Headless Blender 5.2 + addon 73e1b3e: `images.load` and `movieclips.load` on GF02 index-PTS MJPEG MKVs (and a real-PTS control). Record size, frame_duration, clip fps. Pass: non-zero size, frame_duration = N. **Run 2026-11-13 (Blender 5.2.3, no add-on): index PTS pass in 4/4 files (and 20/20 VSE-rendered frames identical); real PTS fail (888 for 891/831/874; 11/20 wrong frames). `results/blender_mkv/FINDINGS.md`** | Whole design |
| DT-B2 | Frame identity at {1, 2, N/2, N} against PyAV decodes; include fill-repeated and fps-mismatch files | Grid, Blender |
| DT-B3 | Patched 73e1b3e addon end to end, route parquet_segments, take with `.mkv` and **no `annotated_videos/`** (or assert every plane filepath ends in `.mkv`); adapt the line-151 count; scene_build_report counts and blender_complete_scene_checks.py:151-160 | Blender |
| DT-B4 | 90° rotated MKV as rotated (4:4:0) pixels vs metadata; Blender image size, orientation and decode | Decision 4 |
| DT-P1 | ffprobe packet pts of a Windows skellycam MP4 written by cv2.VideoWriter (X264): index/CFR or not | §2 claim about today's files |
| DT1 | GF02 Part A through dev-streaming VideoFileMetadata, SequentialVideoReader and RecordingVideoSources, with the chosen av version (and 18.1.0 / 19.0.1). Whether GF02 files still exist is not verified; long files were deleted | FMC reads |
| DT2 | `cv2.VideoCapture(path)` with no API preference on MKV under Windows: getBackendName | FMC reads |
| DT3 | browser_stream on an index MKV: average_rate set; seek to t lands on round(t × rate) | Browser |
| DT4 | Fill-repeated MKV: OpenCV count/seek, PyAV decode, Blender identity | Decision 17 |
| DT4b | Fill-repeated take through posthoc: 3D and filter output with and without null-2D masking | Decision 26 |
| DT5 | OpenCV count and seeks with `cluster_size_limit=1`, small frames (160×90) and large frames | Decision 8b |
| DT6 | Index MKVs at 30000/1001, 59.94, 60 and 120 fps: cv2 count and fps | MKV rate rule |
| DT7 | skellycam lockstep with a camera whose grab or retrieve fails or times out: stall, drop or duplicate? (the normal gate behaviour is known from code, camera_orchestrator.py:118-131) | Decision 17 |
| DT8 | MEAN_CAMERA_TIMES vs multiframe CSV on a real take: CSV text precision difference only | Dropping the CSV |
| DT9 | tj3 lossless rotation: exactness at non-MCU sizes with PERFECT/TRIM; 4:4:0 decode in FFmpeg/OpenCV/PyAV; throughput at 16 × 1080p60 | Decision 4a |
| DT10 | Build a realtime adapter to ObservationRecordingRequest from aggregator output; it passes the arrow_schema validator; saving a realtime run does not drop other runs | Decision 12a |
| DT11 | Live tracking journal: writer-PID kill, recovery, 1-byte flip detection; size and cost of float64 vs float32 records | Decision 12b |
| DT11b | ChArUco cache mapping by `.skvt` source_frame_number on a real take | Decision 19 |
| DT12 | NPY export of OVERLAY_2D + LANDMARKS_3D on a take with a multiframe CSV | Export inference |
| DT13 | Journal fold passes the arrow_schema validator | Decision 12b |
| DT14 | Real arrival_ns round-tripped through float64 timestamp_s | Exact time keys |
| DT-K3 | Synthetic marker at a known pixel through posthoc: read OVERLAY_2D to fix pixel origin and centre convention | §5 spec reference |
| DT-K4 | Produce a new-format reference take (MKV + `.skvt` + Parquet) and run it through the dataset workflow and Blender acceptance next to legacy test_data | End to end |
| DT-S1 | `.skvt` kill test with a direct writer-PID kill (not the uv launcher); records = acked frames | Sidecar |
| DT-A1 | Opus in MKA at 128/256 kbit/s, `cluster_time_limit=100`: kill loss, size, live packet offsets, direct PID kill | Decision 5b |
| DT-A2 | FLAC (`frame_size=1024`) → MKA + `.skat` under direct writer kill; Linux and macOS; real microphones; VLC on a plain `.mka` with no attachment | Decision 5a |
| DT-E1 | JPEG encode throughput for YUYV cameras at target resolutions and rates | Decision 23 |
| DT-C1 | GB/hour per camera and PyAV decode fps through SequentialVideoReader: MJPEG MKV vs today's X264 MP4 (storage and decode cost, not verified) | Cost |
| DT-X1 | GF02 Part A/B plus the `.skvt` kill test on Linux and macOS | Cross-platform |
| DT-R1 | Repair: PyAV remux of a killed index-PTS MKV, rewrite segment_uid/offsets, FMC opens it; also an in-place repair attempt | Repair |
| DT-R2 | Seek to a pts-bumped frame (only relevant if PTS ties ever occur) | Low |
| DT-U1 | Unfinished take in freemocap's recording list: status shows "needs repair", no probe crash | Decision 24 |

---

## Plan and decision-log updates needed (listed, not made)

**New entries recording the reversal itself (proposed):**
- PLAN: a new entry (for example D31) "reverse D27; spec v0 with separate sidecars and tracking Parquet".
- SFF: a new ADR superseding E/SFK5.

**PLAN (CAPTURE_AND_RECORDING_PLAN.md):**
- D27 (PLAN:460): reversed. Its own text says it changed D17, D21 (4)-(5) and D23.
- D15 (PLAN:448) FLAC: restore if Decision 5a; else restate.
- D16 (PLAN:449) embed at finalisation: stays withdrawn under Decision 1a, with a new reason (separate sidecars, not MCAP).
- D17 (PLAN:450) skellyfileformat[write] with MKV writer and appender: reverts, minus the appender.
- D18 (PLAN:451) player draws the frame label from the sidecar: unchanged.
- D19 (PLAN:452) and rule row PLAN:61: restate the "MCAP with JPEG frames and Opus audio (D27, D28, D30)" text.
- D21 (PLAN:454) items (4)-(5): revert to u16 header fields.
- D23 (PLAN:456) spec v0 scope: reinstate with changes (no embed, tracking sidecars, `.skat` not `.skau`).
- D25 (PLAN:458): the rev 3.11 note reverts to the sidecar header.
- D28 (PLAN:461) Opus: restate per Decision 5.
- D29 (PLAN:462) Lichtblick, VLC dropped: revert or restate; "§2.1 Playback outside the app" applies again.
- D30 (PLAN:463) skellysync on MCAP: reverts to Design A (PLAN:25) with a separate `.mka`.
- Rev 3.12 profile choices (PLAN:8-15) and the rev 3.11 note (PLAN:16, 65) revert.
- §2.7 S1-S9 (PLAN:176-186) go live again. S8 needs reconciling with "no manifest" (E/TDB5).
- Row 2.2 (PLAN:397, lockstep removal) now also needs the `filled` flag rule (§8).
- Row 2.4 (PLAN:399) "JPEG in MKV with a sidecar" is valid again, against HO:23.
- §3.1 "Recordings readable by OpenCV" (PLAN:270) holds with index PTS, with the OpenCV 4.12 / development-reader caveat.
- Not D27-dependent: D2, D3, D6, D20, D22, D24, D26.

**Research notes made stale (status headers needed):**
- `docs\tracking_file_decisions_20261113.md` (untracked): its root decision is "freemocap (FMC) writes a separate tracking MCAP per take" (TFD:23). Add a header pointing to this proposal.
- `HANDOFF_20261113_freemocap_phase2_work_items.md` (untracked): framed around MCAP and Lichtblick (HO:23). Add the same header.

**SFF decision entries needing superseding or restating:**
- E/SFK5 (the MCAP switch) and the MCAP ADRs E/HD8Z, E/WD9A, E/X1G6, E/7K3C, E/41VF and E/68Z6, which superseded FGK2, 3KH3, WD1R, CA03, X7FT, M4DF, 25VV and CE4D (PLAN:16). X1G6's revival is close to X7FT ("JPEG in MKV with skellyfileformat sidecars, and FLAC audio", X1G6:18-19).
- MCAP-profile entries E/DK8S, E/TDB5, E/752H, E/FF01, E/QDZ7, E/S4FG and E/10JC (PLAN:15).
- Later accepted entries E/MG7C, E/PV6S, E/D9N1, E/5G42, E/T24G, E/WG08 and E/W4PF.
- Port the container-independent content per entry:
  - 752H: time meanings, clock table, no legacy time, rate bounds.
  - MG7C/T24G: fit rules (if 7b).
  - PV6S: consent prompt and crash read.
  - 5G42: repair marker, audio label, RFC 8785.
  - WG08: states, reasons, warnings, JSON.
  - TDB5: no manifest and take_uuid grouping.
  - 7K3C: versioning.
  - 68Z6: superseded if 4a, kept if 4b.
  - T24G: EXIF rule.
  - W4PF: items 5-6 kept; item 8 superseded by a tracking-sidecar entry.
  - DK8S: items 2, 8, 11.
- open-work.md: the gate-1 and absorb lists (OW:6-33) are MCAP-specific and need rewriting. Provisional items carry over unchanged (OW:34-43).
- Memory note: SPEC.md on main is draft v1 and lags the accepted entries (e.g. MG7C `pos_first`, WG08 `invalid`). Build any new draft from the entries, not from SPEC.md.

---

## Evidence

**Spec and decisions (SFF):**
- `bd62b60:spec/SPEC.md`: S:3, 9-55, 23, 25, 51, 63-66, 135-136, 143-148, 150-158, 160-163, 164-170, 187-188, 204-234, 258-264, 282-293, 295, 305, 315-320, 333-345, 350-351, 358-378, 393, 427-463, 465-596, 598-618, 620-758, 735-744, 741-743, 760-786, 788-818, 820-847, 849-865, 867-889, 891-996, 998-1024, 666, 1013; SFF-003, 050-053, 057, 100-113, 151, 157-159, 162, 165-171, 175-180, 200-208, 251, 257-263, 300-304, 350-363, 400-405, 450-455, 502-504, 550-553, 650-668.
- `bd62b60:spec/conformance.md`: C:25, 51, 101, 123-128, 166, 305, 353, 404, 420, 517, 540, 589, 620, 629, 650; 108 unique SFT IDs.
- `38ad0d6:spec/SPEC.md`:3-6; `38ad0d6:decisions/open-work.md`: OW:6-50.
- Entries: E/SFK5:18-19, 37-44, 52, 68-71; E/3KH3:39, 67-68; E/752H:7-31, 35-39; E/MG7C:5-30, 34-35, 39-40, 57; E/T24G:12-48, 54-59; E/WG08:3, 10-50; E/PV6S:7-29; E/5G42:10-19; E/D9N1:3, 7-30, 51-54; E/TDB5:7-38; E/7K3C:7-35; E/68Z6:5-17; E/W4PF:7-29; E/X1G6:7-19; E/DK8S:7-34; E/FF01:3, 33-35; E/S4FG:39; E/CA03:19-29; E/CE4D:37; E/WD9A:7-31; E/10JC:7-15.

**Research docs (SC\research):**
- `skellycam_recording\docs\spec_v0_review3_20261112.md` R3:3, 5, 9-16, 20-37, 41-49, 53-58; review 1/2 (R2:7); `spec_draft_decisions_20261112.md` DD:13, 51-71.
- `skellycam_recording\docs\tracking_file_decisions_20261113.md` TFD:8, 10, 17, 23-65.
- `HANDOFF_20261113_freemocap_phase2_work_items.md` HO:23, 38-39, 49-53, 58-67, 72-89.
- `CAPTURE_AND_RECORDING_PLAN.md` PLAN:8-16, 25, 61, 65, 176-186, 270, 349, 397, 399, 431-463.
- `skellycam_recording\docs\vlc_playback_rate_20261112.md`:13, 15, 21-30, 34; `mcap_check_20261113.md`:93.

**Results (RES = ...\recording_upgrade\results):**
- EVIDENCE_INDEX.md: EI:40, 53, 54, 56, 59, 64, 72, 109, 110.
- crash_resilience\gapfill\GF02_container_matrix.json (partA[], partB[]), GF02_container_matrix.md, GF02_recovered_rates.txt; crash_resilience\FINDINGS.md:5-6, 52-58, 380-386, §2.1-2.13; crash_resilience\pyav19_recheck.json kill[]; sidecar_durability.md/.json; bench\fragment_overhead_mjpeg_pyav19.json, repair_pyav19.json, fsync_pyav19.json; truncation_pyav19.json.
- jpeg_passthrough\FINDINGS.md:180-186, 370, 379-383, 640, 652-657; bench\bench_rotate_20261110T093546Z.json; bench\open_long.json.
- sidecar_embedding\FINDINGS.md:36, 38, 255, §6.1, §10; small_jpeg_offsets.json; audio_offsets.json S4-S6; spec_checks.json; matrix.json; big.json.
- audio_skellycam\FINDINGS.md:9, 21, §2.1, §2.2, §4; crash_kill.json; bench.json; align.json; scripts\audio_skellycam\crash_kill.py:60-68.
- flac_skau\flac_skau.json, recovery_check.json, FINDINGS.md:76-80, §8, vlc_check.json, electron_e35.json, electron_e45.json.
- audio_skellysync\FINDINGS.md:18, 69, 89, 96-106; frame_count_vs_audio.json.
- rotation_flag\FINDINGS.md §0, §3; overlays\FINDINGS.md:133, 484, 630; overlays\bench\bench_overlay_cost_20261110T103707Z.json, verify_method_crash_modes.json; scripts\overlays\overlay_model.py:288-293; sidecar_load\summary.json; chromium_sync_scrub\gapfill\GF08_ts_sync.json; mcap_kill\FINDINGS.md "Problems found" 1; tracking_sync\summary_gpu.json.
- scripts\jpeg_passthrough\jp_io.py:353-363.

**freemocap `upstream/development-streaming` @c27fc299 (FMC):**
- core/pipeline/posthoc/video_group_helper.py:14, 133-142, 149, 188, 322-333, 337-343, 373-401, 440-442; video_node.py:178-269, 350-397, 401-509; mocap_video_node.py:147-152; annotation_output.py:19, 36-41, 58-65, 75-110.
- core/pipeline/dataflow/video_sources.py:46-56, 160-168; scientific_recording.py:21, 162, 185-224, 228-252, 255-320; annotation_workers.py:42-56; recording_pipeline.py:210, 256-363.
- core/reconstruction/posthoc_filtering.py:50-56; recording_timing.py:20-48.
- core/tasks/mocap/posthoc_mocap_task.py:120-138, 170-177, 237-313; mocap_helpers/recording_framerate.py:16-18, 29-39, 91.
- core/recording/sample_encoding/arrow_schema.py:15-30, 108-145, 196-197, 233-258; sample_encoding/observation_samples.py:29-47, 98-139, 153-245; spatial_points.py:24-101; reconstruction_samples.py:166-301; diagnostic_samples.py:16-51; fit_channels.py:18-57.
- core/recording/result_processing/observation_inputs.py:40-52, 167-175, 212-253; observation_publication.py:86-233, 240-248; saved_observations.py:40-114.
- core/recording/data_descriptors/recording_descriptor.py:34-44, 98-111, 191-196; recording_model.py:15-27; channel_series.py:73; parquet_storage/parquet_writer.py:28-91; recording_info.py:9-47; exports/wide_csv.py:26-319; tall_csv.py:26-106.
- core/types/derived_point_name.py:7-8; channel_kind.py:6-26.
- core/tasks/calibration/shared/calibration_paths.py:13-39; calibration_save.py:21-51; calibration_toml.py:38-224; camera_model.py:18; anipose_calibration/helpers/anipose_calibration_helpers.py:138-146.
- core/pipeline/realtime/charuco_recorder_node.py:30-31, 42, 96-104, 158-231; realtime_pipeline.py:255, 349-351; camera_node.py:292-295.
- api/http/playback/playback_router.py:75-110, 244-273, 300-305, 549-625, 688, 707-736, 760-845; api/http/mocap/mocap_router.py:14-15, 49, 89, 141, 160-178, 237, 299-372; api/http/calibration/calibration_router.py:133, 178-189; api/websocket/websocket_server.py:42, 118-182.
- core/playback/media_selection.py:8, 16-26; system/recording_status/recording_status.py:20, 113-135, 148-149, 170-190; system/recording_structure/recording_structure.py:13-22, 88-145; system/default_paths.py:12-13, 57-73.
- core/blender/export_to_blender.py:30-45; local_package.py:16-80.
- utilities/extract_camera_id_from_video_path.py:3, 25; utilities/get_video_paths.py:8-9.
- freemocap/tools/datasets/catalog.py:36, 41; inspection.py:80, 92-97; preparation.py:364, 371; scientific_comparison.py:122, 131; stage_matrix.py:200; workflow.py:173; full_recording_comparison.py:43, 46.
- RECORDING_CONTRACT.md:20-27, 55-58, 67, 78, 115-133, 221; current-work-plans/03-transport/recording-folder-contract.md:33-53, 199-200; shared/recording-contract/paths.json:3-24.
- freemocap/tests/test_posthoc_observation_recording.py:131-148; test_recording_store.py:422; test_blender_preparation.py:61; test_dataflow_scientific_recording.py:156, 197, 207, 233; pipelines/mocks/mock_camera_group.py:73-75; reference_recordings/test_fresh_posthoc.py:37-41.
- freemocap-ui/src/components/playback/usePlaybackController.ts:39-41, 54; src/services/recording/browser-video.ts:78-84; src/store/slices/cameras/cameras-types.ts:18, 59-60; electron/main/api.ts:26, 307, 364; src/store/slices/active-recording/layout-presets/layout-presets.yaml:25; recording-structure.ts:141, 151.
- pyproject.toml:8, 17, 50-57; uv.lock:123-128, 147-152, 783-785, 1670-1671.

**skellycam `remotes/upstream/development-streaming` (SCds):**
- skellycam/core/recorders/videos/recording_info.py:47-60, 68-104, 128-134; video_filename.py:7-8, 27-28; recording_metadata.py:8-27; video_associations.py:12-48; video_file_metadata.py:21-46; sequential_video_reader.py:16-64; browser_stream.py:44-108; pyav_video_writer.py:4-6, 14, 33; video_recorder.py:52-55, 96-100, 120-134; fourcc_codec_helpers.py:13-16, 54-58, 71-76; video_copy_plan.py:34-39; video_derivation.py:22-32.
- skellycam/core/recorders/recording_finalizer.py:24-31, 53-71, 147-171.
- skellycam/core/timestamps/recording_timing_reader.py:13-31, 51-117; numpy_timestamps/create_camera_csvs.py:15-178; create_multi_frame_csvs.py:13-121; process_and_save_recording_timestamps.py:37-48; recording_timestamp_stats.py:44-147.
- skellycam/core/types/numpy_record_dtypes.py:49-84; core/recorders/audio/audio_recorder.py:121-162; core/camera_group/camera_group.py:200-207, 239-240; camera_orchestrator.py:102-131; core/camera/config/camera_config.py:27-29, 156-164; system/default_paths.py:6-8; recording_statistics.py:13-29; pyproject.toml:55, 68.

**Blender addon:**
- A73 (73e1b3e): core_functions/parquet_scene.py:158-229, 259-262; parquet_import.py:28-40, 196-219; load_videos/load_videos.py:9-17, 29-36, 64, 95-199, 228, 250-303, 319-329; add_capture_cameras/add_capture_cameras.py:42-87, 130-216; freemocap_data_handler/parquet_recording.py:14-118; utilities/recording_framerate.py:17-79; main_controller.py:145-155, 372-375; tests/blender_complete_scene_checks.py:148-161; tools/reference_data.py:55; TESTING.md:24.
- INST (980ae856): freemocap_blender_addon-2026.4.1041.dist-info/direct_url.json; add_capture_cameras.py:153-157; load_videos.py:8-16, 264-267.

---

Re-checked for this revision: the citations named in the verifier issues (crash_resilience FINDINGS and pyav19_recheck.json, fragment_overhead bench, sidecar_embedding FINDINGS:255, vlc doc:34, S:150-158 and 340-378, camera_orchestrator.py, PLAN:349/397, scientific_recording.py, video_recorder.py, pyav_video_writer.py, fourcc helpers, recording_info.py, recording_finalizer.py:55, audio_skellycam FINDINGS and bench.json, crash_kill.py, flac_skau FINDINGS, audio_skellysync FINDINGS, jpeg_passthrough FINDINGS, overlay_model.py, overlays FINDINGS, sidecar_durability.md, the A73 Blender test, parquet_import and parquet_scene, recording_timing.py, create_multi_frame_csvs.py, saved_observations.py, conformance headings, R3:53-58, 752H:28-31, TFD rows, FMC and SCds pyproject, cameras-types.ts, observation_publication.py:245, mocap_router.py:335-366, Electron api.ts, local_package.py, the test-file count, catalog.py and inspection.py, and EI:40/53/54/109/110). Other citations are carried over from the reader reports without re-opening the file. No tests were run.
Risks: Blender decoding MJPEG MKV (DT-B1) is unproven and is the reason for the reversal. Every "FreeMoCap reads exactly" result used the old development reader, not dev-streaming's PyAV reader (DT1). Either result can force the export fallback.
