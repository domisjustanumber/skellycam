# python_integration: adversarial verification, methodology lens

2026-11-09, Gerald. Scope: the draft FINDINGS for python_integration (not on disk). This pass looks for confounders, test artefacts and conclusions that don't follow from the evidence. No timing was measured.

**Paths:** `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`, `S/` = `.../scripts/python_integration/`, raw = `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/`.

**New evidence from this pass:**
- `R/verify_method_checks_pyav19.json`, made by `S/verify_method_checks_pyav19.py` with PyAV 19.0.2 (FFmpeg 9.0.2) and opencv-python 4.12.0.88. It is functional only (under 1 min CPU, no timing) and covers:
  1. container-level demux and decode of the PyAV 19 killed and truncated files, with packet flags kept;
  2. killed-file sizes checked against multiples of 32 KiB;
  3. the VFR compat clips re-made three ways (original PTS pattern, jitter only with no 67 ms gap, and the original shifted so the first PTS is >= 0), each probed with `cv2_read_probe.probe_clip`.
- Media from this pass is in `raw/verify_method_vfr/`.
- Run it from the repo root: `uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/verify_method_checks_pyav19.py research/skellycam_recording/recording_upgrade/results/python_integration/verify_method_checks_pyav19.json`

## 1. Refuted

### R1. "Neither PyAV nor cv2 flags the torn frame" / "the sidecar CRC is the only torn-frame detector for fMP4/AVI" (F4, F5, implication 4)

**Why it's wrong**
- The PyAV 19 lean re-check rebuilt the last packet from bare bytes with `av.Packet(last)` and a fresh `CodecContext` (`S/pyav19_recheck.py`, `lean_probe`). That throws away the demuxer's packet flags, so the re-check could not have seen a corrupt flag even if one was set.
- **measured** (`R/verify_method_checks_pyav19.json` → `killed_container_decode`, `truncated_container_decode`): demuxing the same files through the container gives `packet.is_corrupt == True` on the torn last packet:
  - `killed.mp4f.real.mp4`: packet 297 (22,583 B);
  - `killed.avi.index.avi`: packet 297 (48,476 B);
  - `cut_50pct.mp4f.real.mp4`: packet 149;
  - `cut_90pct.avi.index.avi`: packet 270.
- **measured** (same file): no packet in the MKV files is flagged, because MKV never returns a partial packet.
- **measured** (same file): `frame.is_corrupt` stays False on every decoded frame. The flag is set on the packet and does not reach the frame.
- **measured, PyAV 18 - background** (`R/crash.md` column `pyav_corrupt_flagged`): 0 everywhere. That column counts frame-level flags only, so it does not contradict the packet-level result.

**Correction**
- Say: "PyAV 19 marks the torn tail packet in fMP4 and AVI with `packet.is_corrupt` (AV_PKT_FLAG_CORRUPT, measured). Frame-level `is_corrupt` stays False, and cv2 gives no flag."
- A reader that works at packet level can detect a torn tail. The sidecar CRC is still the stronger check, because it also catches same-length corruption and a missing tail.
- Implication 4 should say: "sfn26's `sequential_video_reader` checks frame-level `is_corrupt`, which is never set here."

## 2. Weak: true as measured, but over-generalised or confounded

### W1. The VFR seek and count errors come from the simulated 2-frame drop, not from VFR jitter (F3, implication 2)

- **code:** `S/make_compat_clips.py:54-56`. `vfr_pts_ms` adds a 67 ms gap after frame 60 ("a drop") on top of ±3 ms jitter. The draft never mentions the gap.
- **measured** (`R/verify_method_checks_pyav19.json` → `vfr`): with **jitter only**, `mjpeg_mkv` gives count 120.0 and `mjpeg_mp4frag` gives count 120.0, and both seek exactly to all 11 targets. With the original pattern, the draft's errors come back:
  - MKV count 122.0, seek 119 → 117;
  - fMP4 seeks off by one after frame 59.
- **measured** (`R/pyav19_recheck_roundtrip_crash.json`): on real camera timestamps, MKV real-PTS gives a wrong count on **1 of 7 sets**:
  - c930e: 888 vs 891;
  - c922_720p_flash: 893 = 893, correct;
  - the 5 synthetic-timestamp sets: correct.
- **inferred:** cv2 derives the count from duration × the nominal `avg_frame_rate` of 30.
  - The c930e delivers about 30.1 fps (fMP4 `cv2_fps_prop` 30.0999), so the count is short. The c922 delivers 30.0055 fps.
  - So the error grows with how far the camera's rate drifts from nominal, with recording length, and with dropped frames, not with jitter.
- **Fix:**
  - Restate the reason: cv2 count and seek go wrong when the PTS timeline holds gaps (drops) or drifts from the nominal rate. Jitter of ±3 ms alone was harmless. CFR index PTS are still the right recommendation, for this more specific reason.
  - Add a caveat: seek accuracy was never tested on the camera-byte files, neither CFR nor VFR. Seeks were only tested on 120-frame PyAV-re-encoded barcode clips.

### W2. "MKV is the preferred container for G2" doesn't follow from the kill test (implication 3, comparison table)

- **measured** (`R/verify_method_checks_pyav19.json`, `bytes_mod_32KiB`): the killed MKV and AVI files are both exactly 23,068,672 B = 704 × 32 KiB. The killed fMP4 file is 704 × 32 KiB + 28 B.
- **measured** (killed size minus recovered size, sizes in `R/pyav19_recheck_roundtrip_crash.json`): each killed file holds about 43 KB beyond the 297 good frames:
  - MKV 43,044 B;
  - AVI 43,724 B;
  - fMP4 16,984 B, but its recovered file carries fragment headers.
- **inferred:** the cut point is set by FFmpeg's AVIO write buffer, not by the container.
  - All three containers lose about the same data at a kill.
  - MKV's demuxer silently drops the partial block: the log shows "File ended prematurely" (`R/pyav19_recheck_run.log`). fMP4 and AVI return the partial block, flagged at packet level (R1).
  - So the draft's inference that "MKV's cluster buffer explains 297 of 300" is at best partial.
- **measured:** a killed fMP4 file opens in cv2 with FRAME_COUNT 298.0 = 298 frames grabbed, so it is usable without recovery except for one torn last frame. MKV gives −2.77e17 and AVI gives 0.0.
- **Fix:**
  - Present the trade-off, not a preference:
    - MKV hides the torn frame but needs recovery before any cv2 count is valid.
    - fMP4 keeps a consistent count without recovery, but shows a torn last frame that `packet.is_corrupt` and the sidecar CRC can detect.
  - The choice also depends on fMP4's open cost on long files, which is pending tonight (`pi_recwriter_cost` phase C).

### W3. The truncation test (F5) runs on cleanly closed files, so the count results are artefacts

- **code:** `S/test_crash.py:143-160`. Part B truncates a file that was already closed, so the duration in the header (MKV) and `avih`/`strh` (AVI) is already final. That is why cv2 reports 300.0 at every cut.
  - A crashed or disk-full file never has that duration: part A gives −2.77e17 for MKV and 0.0 for AVI.
- **measured:** the "−1 byte" cut only removes trailer/index bytes (300 exact packets in all three containers), so it never cuts inside a frame, despite the docstring (`S/test_crash.py:8`).
- **Fix:**
  - Keep the per-packet results (exact prefix, torn tail).
  - Drop "header count (300) > frames read" as a crash property, or label it "artefact of truncating a finalised file".
  - The realistic failure is the part A kill (one per variant).

### W4. F2 sample and overhead numbers

- **measured** (`R/pyav19_recheck_roundtrip_crash.json` → `timestamps`): only the two 720p flash sets use real camera timestamps. The five 10-19-frame sets use "synthetic: 30/60 fps lattice +-2 ms deterministic jitter".
  - `sidecar_ts_exact` and `sidecar_fn_exact` are close to tautological: the writer stores the input integers.
- **measured:** the per-frame overhead on 10-19-frame files is dominated by the fixed header:
  - AVI index: 323.7-593.1 B on the short sets vs 30.9 B on the 891-frame set;
  - MKV: 69.6 B at 1080p (19 frames) vs 45.2 B at 720p (891 frames).
- **Fix:**
  - Say "byte-exact on 1,862 real camera JPEGs; real timestamps on 2 sets (1,784 frames), synthetic on 5".
  - Drop the 1080p overhead figure, or mark it as header-dominated (19 frames).

### W5. F7 drop-policy result carries no information

- **code:** `S/recwriter.py` `RecorderThread.submit`. An unpaced loop of 120 `put_nowait` calls likely finishes inside one GIL switch interval (inferred), so the writer thread may never have run. 118 dropped is what that setup guarantees.
- **Fix:**
  - Report it only as "drop path works: packets = submitted − dropped, files consistent".
  - Remove the inferred sentence about bursts.
- **Not tested:** a kill with a full queue (queued frames are lost; the sidecar stays consistent because it is written after mux).

### W6. PyAV 19 bump rationale (implication 6)

- **code:** the 18.0.0 wheel already releases the GIL around `av_interleaved_write_frame` (`av/container/output.py:627-628`, 18.0.0 uv-cache copy). 19.0.2 adds header (:656-657), trailer (:84-85) and closep (:95-96).
- The benefit is per open/close and was not measured.
- **code:** the repo declares `requires-python = ">=3.11"` (`pyproject.toml:5`), and PyAV 19 drops Python 3.11 (CHANGELOG, as cited in the draft). The bump needs that changed too. The draft only mentions the `av>=12.0.0` pin.
- **Fix:**
  - Mark the GIL benefit "source, not measured".
  - Add the requires-python change.

### W7. "CFR files are exact in every reader tested"

- "Readers" means cv2 4.12 / 5.0 CAP_FFMPEG and PyAV.
- The exact-seek results are on PyAV-re-encoded barcode clips. The camera-byte CFR files (MKV/AVI index) were checked only for count, and for `grab()` count on one set.
- **Fix:** name the readers and the clip type. Chromium pixel playback is cross-topic and was not verified here.

### W8. F9 PyAV vs cv2 pixel difference: an alternative explanation is not excluded

- Agreement was checked on frame 0 of each set only.
- The 6-24 difference may come from swscale's yuvj422p → bgr24 conversion (chroma upsampling, coefficients), not from the mjpeg decoder.
- This was not isolated. The recommendation ("one decoder per pipeline") still holds.

## 3. Confirmed / upgraded

- **F10 inference → measured** (`R/verify_method_checks_pyav19.json`): `av1svt_mp4_orig_nonneg` decodes 120 frames, and its sequence is exact. Both variants with a −3 ms first PTS decode 119.
  - The encoder emits a first packet of pts −3 at 1/1000 (`encoder_first_packets`).
  - The negative first PTS is the cause, as the draft inferred. The remaining off-by-one seeks (77 → 78, 119 → 118) are the 67 ms gap (W1).
- **F8 codec list:** the 18.0.0 and 19.0.2 probes differ only in versions, type names and the version-tagged fields. The `codecs` entries are equal (diff of `R/pyav_version_probe_*.json`).
- **F7 GIL source:** confirmed in the 19.0.2 wheel's `av/container/output.py` at the lines cited.
- **F4 MKV −2.767e17** matches (INT64_MIN / 1000) × 30. The draft labels this inferred, which is right.
- **Bench state:** no timed python_integration result exists. Only `--quick` smoke files are in `R/bench/`. The draft keeps timing out.

## 4. Bench requests for tonight (PyAV 19.0.2)

1. **`pi_recwriter_cost` under PyAV 19.0.2 without touching the venv.** The manifest command uses `.venv` (PyAV 18). It covers MKV vs fMP4 open/count cost, which decides W2.

```
cd /c/Users/Dom/GitHub/freemocap/skellycam && uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_recwriter.py --tag quiet1_pyav19
```

2. **`pi_jpeg_decode_cpu` with PyAV 19.0.2.** The script's PEP 723 header pins `av==18.0.0`, so this command bypasses the header with `--no-project --with`.

```
cd /c/Users/Dom/GitHub/freemocap/skellycam && D=/c/Users/Dom/AppData/Local/Temp/pi_ljt && mkdir -p $D && ( [ -f $D/bin/turbojpeg.dll ] || ( curl -sSfL -o $D/ljt.exe https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0-vc-x64.exe && echo "662761d8ba8dae04aec74023ebaeceb856c2b56b9b59cfd180759d26300dda42 *$D/ljt.exe" | sha256sum -c && "/c/Program Files/7-Zip/7z.exe" x -y -o$D $D/ljt.exe > /dev/null ) ) && uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with opencv-python==4.12.0.88 --with simplejpeg==1.9.0 --with PyTurboJPEG==2.6.1 python research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_jpeg_decode.py --tag quiet1_pyav19 --turbojpeg-dll "$D/bin/turbojpeg.dll"
```

The `--with` list in the second command matches the script's whole PEP 723 dependency list (`S/bench_jpeg_decode.py:3-9`), with av changed to 19.0.2.
