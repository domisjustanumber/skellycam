# jpeg_passthrough: VERIFY_method (methodology review of the draft FINDINGS)

2026-11-09, Gerald. Adversarial review of the draft FINDINGS (given to the verifier as text). The lens is methodology: confounders, unrepresentative corpora, single runs, functional passes taken for compatibility, and conclusions that don't follow.

No timing was measured. Every new check is functional, PyAV 19.0.2 writer, under 1 min CPU. Paths are relative to `research/skellycam_recording/recording_upgrade/` unless absolute. Media went to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/verify_*` and was deleted.

## New checks run for this review

| Script (`scripts/jpeg_passthrough/`) | Result file (`results/jpeg_passthrough/`) | What it tests |
|---|---|---|
| `verify_method_writer.py` (uv, av==19.0.2) | `verify_method_writer.json` | V1: is every input JPEG present verbatim, in order, in the raw container bytes (no FFmpeg demuxer involved)? V2: writes c930e_720p_flash with realistic drops (`gap60`: frames 300-359 removed, a 2 s gap, 831 frames; `drop50`: every 50th frame removed, 874 frames), real timestamps kept. V3: a 54,000-frame (1,796 s) fMP4/MP4 1/1e6 of tiny synthetic JPEGs with one 2 s gap |
| `verify_method_reader.py` (skellycam .venv, OpenCV 4.12.0, read-only use) | `verify_method_reader.json` | OpenCV count, frames read and seek, plus FreeMoCap `VideoHelper` reads **matched against OpenCV's own sequential decode** on the V2/V3 files |
| `verify_method_size_check.py` (uv, av==19.0.2) | `verify_method_size_check.json` | Whether the 1-3 B size difference comes from in-memory vs file writes |
| `pyav19_recheck.py --child` + `verify_method_killed_readers.py` (.venv reader) | `verify_method_killed_readers.json` | OpenCV 4.12 and FreeMoCap on hard-killed files **written by PyAV 19.0.2** (fMP4 1 s 1/1e6, fMP4 per-frame, MKV, NUT) |
| `bench_open_long.py --dry --frames 300` (uv, av==19.0.2, opencv-python 4.12.0.88) | `verify_method_open_dry.json` | Smoke test of the bench requested below. It checks only counts, with no timing |

## Refuted

### R1. "Frame-exact seeks" in OpenCV for fMP4/MP4 (§2.4, §3.1 seek row, §3.2, §4.2)

- The draft claim: fMP4 1/1e6 "gives OpenCV/FreeMoCap exact counts and seeks on a clean file" (§4.2), based on 10/10 seeks on c930e_720p_flash.
- **measured** (`verify_method_reader.json`): when frames are dropped, OpenCV `CAP_PROP_POS_FRAMES` seeks land on the wrong frame:

  | File (PyAV 19.0.2, 1/1e6 unless MKV) | frames | OpenCV count | frames read | seek exact | FreeMoCap count / reads matching OpenCV's sequential decode |
  |---|---|---|---|---|---|
  | gap60 fMP4 1 s | 831 | 831 | 831 | **5/10** | 831 / 4 of 4 |
  | gap60 fMP4 per-frame | 831 | 831 | 831 | **5/10** | 831 / 4 of 4 |
  | gap60 MP4 | 831 | 831 | 831 | **5/10** | 831 / 4 of 4 |
  | gap60 MKV | 831 | 888 | 831 | 5/10 | 888 / 3 of 4 (frame 887: "Failed to grab frame") |
  | drop50 fMP4 1 s / per-frame / MP4 | 874 | 874 | 874 | **7/10** | 874 / 4 of 4 |
  | drop50 MKV | 874 | 888 | 874 | 5/10 | 888 / 3 of 4 |

- Why this happens:
  - OpenCV turns a timestamp into a frame number through the average fps: `return (int64_t)(get_fps() * sec + 0.5);` (source: OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp:1992-1996`, local copy `.../93366190-.../scratchpad/jpeg_passthrough/src/cv412_cap_ffmpeg_impl.hpp`).
  - With a gap in the capture, frame index and time × fps no longer agree.
  - The c930e set has no such gap.
- The case is realistic. Today's recordings: "A camera that drops frames or really runs at 29.97 or 25.7 fps still gets a header of 30" (code review: `research/skellycam_recording/REPORT.md:343`).
- FreeMoCap is not affected:
  - Its `VideoHelper` reads forward with `grab()` (code: freemocap 5632778a `video_group_helper.py:235,246`).
  - It never uses `CAP_PROP_POS_FRAMES` (code: grep of that file finds no match).
- **Correction:**
  - With a 1/1e6 time base, OpenCV's frame count is exact for MP4 and fMP4 even with gaps (831, 874 and 54,000 frames; measured: `verify_method_reader.json`).
  - FreeMoCap's forward reads return the right frames.
  - OpenCV `CAP_PROP_POS_FRAMES` seeking is exact only when the capture has no gaps, in every container tested.
  - A random-access consumer (the UI, or any analysis that seeks) must seek by timestamp from the per-frame sidecar, not by OpenCV frame index.

### R2. "Its file sizes differ from file writes by 1-3 B" (§6 coverage gaps, also §2.1)

- **measured** (`verify_method_size_check.json`, PyAV 19.0.2, c930e VFR 1/1e6 pts): in-memory and file writes are the same size in every container checked:

  | Container | in memory | file |
  |---|---|---|
  | MKV | 49,354,774 | 49,354,774 |
  | MP4 | 49,325,753 | 49,325,753 |
  | NUT | 49,339,897 | 49,339,897 |

- **Correction:** the 1-3 B difference is between PyAV 18 and PyAV 19 writes. Example: MKV VFR 49,354,777 B in `mux_matrix.md` line 56 vs 49,354,774 B. Its cause is NOT VERIFIED. The in-memory method does not change sizes, so it is not a coverage gap.

### R3. OpenCV 5.0.0.93 table: "MP4, MOV, fMP4 (1/90000 and 1/1e6) exact, 10/10" (§2.4)

- **measured** (`version_bump.json` rows): the containers read by OpenCV 5 are mkv, webm, mp4, fmp4_1s, fmp4_perframe, mov, avi, nut, mjpeg_raw_mux, avi_tb_rate, mp4_tb_us, mov_tb_us and nut_tb_us. **There is no fMP4 1/1e6 row.**
  - code: `scripts/jpeg_passthrough/jp_io.py:31-49` `CONTAINERS` has no fMP4 1/1e6 entry.
  - code: `version_bump_check.py:47` loops over `io.CONTAINERS`.
- **Correction:** read "MP4 and MOV (1/90000 and 1/1e6), fMP4 1 s and per-frame (1/90000)". fMP4 1/1e6 was read only by OpenCV 4.12.0 (`pyav19_fmp4_tb_us_readers.json`). The note under table 3.1 already says this. Section 2.4 contradicts it.

## Weak (keep, but fix the wording or scope)

| # | Draft claim | Problem | Fix |
|---|---|---|---|
| W1 | "max error 0 µs on all 7 sets" (§2.3) | Only 2 sets have real timestamps (c930e, c922 720p flash). The other 5 replay c930e's first 10-18 intervals (720p60 at half), over 10-19 frames (code: `pyav19_recheck.py:58-60,152-160`; `jp_common.py:59-67` "real capture jitter, borrowed"). So "7 sets" means 2 independent timestamp series | Say "2 real timestamp series (891/893 frames) plus 5 short sets that reuse c930e intervals" |
| W2 | "keep the real timestamps exactly" (§2.3) | The source is MF sample time at 100 ns resolution (code: `jp_common.py:22-23`). The scripts floor it to µs before muxing (`(t - ts[0]) // 1000`, `pyav19_recheck.py:156`) and compare against the floored values. The sub-µs part is never stored | "exact at 1 µs resolution (inputs floored to µs); keep ns in the sidecar" |
| W3 | "seek 10/10" (whole draft) | Seek targets are `[0,1,2,n//3,n//2,n-2,n-1,5,n//2,3]` (code: `jp_io.py:332`): 5 targets are in the first 6 frames, and n//2 appears twice. "Exact" means it matches the same reader's sequential decode, not the input frame. 10/10 therefore rests on about 4 informative positions | Report the targets. See R1 for the gap failure |
| W4 | "FreeMoCap VideoHelper frame_count 891, with 4/4 reads ok" (§2.4, table 3.2) | `fmp4_tb_us_cv2_check.py:45` passes `ref_hashes=None`, so "ok" only means no exception. It does not show the right frame came back | Now checked: 4/4 reads match OpenCV's sequential decode on the gap60/drop50 fMP4 files (measured: `verify_method_reader.json`). Cite that |
| W5 | Kill table §2.5 and table 3.2 "578 vs 596" | A single kill point, after complete `mux()` calls (code: `pyav19_recheck.py:163-184`). The killed MKV, AVI, NUT and raw files are all exactly 33,030,144 B = 1008 × 32,768 (measured: `pyav19_recheck.json` `C_killed.*.bytes`). So their 597-598 survivors reflect where the user-space write buffer happened to stop (inferred: AVIO buffer). The differences between those containers are not container properties. fMP4 1 s loss (22 frames) depends on the kill's phase within the fragment | State the loss as a bound: "unflushed write buffer (32 KiB here, inferred), plus the open fragment for fMP4 (up to about 1 s at 1 s fragments, inferred)". Mark 578/596 as one sample |
| W6 | "fMP4 ... stays readable after a kill" (§4.2) and kill reader table (PyAV 18 only) | Re-run with **PyAV 19.0.2 writers** (measured: `verify_method_killed_readers.json`, OpenCV 4.12): fMP4 1 s count **582** vs 579 read, and FreeMoCap read of frame 581 fails. fMP4 per-frame count **597** vs 596 read, and frame 596 fails ("Failed to retrieve frame 596"). MKV count -276701161105643264, FreeMoCap ValidationError. NUT count 595 vs 598 read. This matches PyAV 18 and adds the per-frame row the draft lacks | "Readable by PyAV/ffprobe after a kill. FreeMoCap needs the count from the sidecar (or a remux on recovery), because OpenCV over-counts by 1-3." Move these rows from background to measured PyAV 19 and drop the §6 "not re-run" item for them |
| W7 | Partial last frame (§2.5) | The cut last JPEG is decoded without error. OpenCV reads 579 frames from the killed fMP4 1 s, but only 578 packets are byte-exact (measured: `verify_method_killed_readers.json`; `pyav19_recheck.json` `C_killed.fmp4_1s_tb_us`). A corrupt frame therefore enters analysis silently. No implication covers this | Add to §4: on recovery, trust only frames that the sidecar records as complete, or check that each packet ends with EOI |
| W8 | "CAP_MSMF reads MKV" (§2.4, table 3.1) | MKV VFR: MSMF read 888 of 891 frames (measured: `version_bump.json`, `cv5_MSMF`) | "MKV partly (888/891 on VFR)" |
| W9 | Overhead table §2.1: MOV 11,139 B, NUT 25,376 B | These are the 1/90000 rows. Table 3.1 uses the 1/1e6 rows (MOV 11,843 B, NUT 26,908 B; measured: `pyav19_recheck.json` `mov_tb_us|vfr`, `nut_tb_us|vfr`). They are unlabelled, so the two tables look inconsistent | Label the time base in every row |
| W10 | "opencv-python 5.0.0.93 gives the same counts and seeks as 4.12.0" (§2.8) | Not an isolated comparison. The 4.12 numbers are on PyAV 18-written files (`mux_matrix.json`); the 5.0 numbers are on PyAV 19-written files (`version_bump_check.py`). opencv-python 5.0.0.93 also bundles its own FFmpeg: avformat 61.7.100 (measured: `version_bump.json` meta) | "The PyAV 18 + OpenCV 4.12 and PyAV 19 + OpenCV 5.0 pairs gave the same counts/seeks on c930e" |
| W11 | Chromium "decode every test JPEG" (§2.6) | The evidence is the decoded dimensions and a mean value (`img_mean`) per image (measured: `electron_check.json`). There is no comparison of pixels against a reference decoder. Only the DHT-stripped vs original equality (both 128.16276) compares two decodes | "decodes (dimensions correct; mean equal for stripped vs original); pixels not compared to a reference" |
| W12 | Rotation: Rust's `tjTransform` returns -1 on generic, so frames stay unrotated (§2.7, §4.8) | The -1 was measured with libjpeg-turbo 3.2.1. The Rust build downloads a turbojpeg static lib "from the latest GitHub Release on the `jonmatthis/openpnp-capture` fork" (code: `git show upstream/sfn26:skellycam-rust/build.rs:1-6`). That version is not pinned and is NOT VERIFIED | Mark the Rust-behaviour inference as conditional on that library's version |
| W13 | "have FreeMoCap count frames from the sidecar or a PyAV packet count" (§4.5) | PyAV `stream.frames` is 0 for fMP4 and MKV, and 300 only for plain MP4 (measured: `verify_method_open_dry.json`). A PyAV count needs a full demux pass, and its cost is pending (bench request 1) | Say "sidecar, or a full PyAV demux pass (cost pending)" |
| W14 | MKV count "6/7 exact" (background) reads as mostly fine | MKV's OpenCV count comes from duration × 30 (fps_prop 30.0). It was wrong on every new variant: gap60 888, drop50 888, and 299 of 300 on looped near-CFR frames (measured: `verify_method_reader.json`, `verify_method_open_dry.json`) | Strengthens §4.4: for MKV, the count is wrong whenever timing is not perfectly regular |

## Confirmed by independent re-check

- **Payload stored verbatim, checked without FFmpeg.** All 891 c930e input JPEGs were found verbatim, in order and without overlap, in the raw bytes of fMP4 1 s, fMP4 per-frame, MP4, MOV and NUT (1/1e6) and MKV (measured: `verify_method_writer.json` `V1_verbatim`). This removes the "same library muxes and demuxes" confounder from the 194/194 byte-exact claim.
- **Frame counts with gaps and long files.** fMP4 (1 s and per-frame) and MP4 at 1/1e6 give the exact OpenCV 4.12 count with drops (831, 874) and on a 54,000-frame, 1,796 s file with a 2 s gap. On that file, 54,000 frames were grabbed and FreeMoCap read frames 0, 1, 27000 and 53999 without error (measured: `verify_method_reader.json` `long_*`). This holds although fMP4 has no `nb_frames` (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe` `nb_frames` null), so OpenCV estimates the count (source: `cap_ffmpeg_impl.hpp:1984-1989`).
- The counts in the draft check out against `pyav19_recheck.json`:
  - 210 attempts, 16 not written (14 WebM plus c930e AVI VFR × 2), 194 of 194 byte-exact;
  - 1,862 frames per container and mode;
  - c930e overheads.
- Killed-file sizes and packet counts are identical between PyAV 18 (`truncation.json`) and PyAV 19 (`pyav19_recheck.json`).

## Pending tonight's bench (added by this review)

- **Open cost and count for long recordings.** FreeMoCap opens every file with `cv2.VideoCapture` + `CAP_PROP_FRAME_COUNT` (code: `video_group_helper.py:151,159`). fMP4 has no `nb_frames`, so the demuxer has to walk every fragment. A 30-minute file with per-frame fragments has 54,000 of them. The open time per container is untested.
  - Script: `scripts/jpeg_passthrough/bench_open_long.py`. It was smoke-tested with `--dry` (counts only, no timing; `verify_method_open_dry.json`).
  - It also times a full PyAV demux packet count (see W13).

## Verdict

- The core G1 result stands: PyAV 19.0.2 `add_mux_stream` stores camera JPEGs byte-exact, now also confirmed without an FFmpeg demuxer.
- Three statements are refuted:
  - R1: OpenCV frame seeks are not exact once the capture drops frames, in any container tested.
  - R2: the in-memory vs file size claim.
  - R3: fMP4 1/1e6 was never read by OpenCV 5.
- R1 changes §4.2 and §4.5:
  - fMP4 1/1e6 is still the leading candidate, because counts stay exact with gaps and on long files;
  - but "frame-exact seek" must come from the sidecar timestamps, not OpenCV;
  - and FreeMoCap needs the sidecar count after a kill (OpenCV over-counts by 1-3, re-measured on PyAV 19 files).
- The kill comparison between MKV, AVI, NUT and raw reflects where the write buffer stopped, not container robustness.
