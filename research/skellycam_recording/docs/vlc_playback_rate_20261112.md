# Do skellyfileformat recordings play at the correct rate in VLC? (2026-11-12)

Provenance: a sub-agent answered from the recording-upgrade FINDINGS and ran one synthetic desk test (VLC 3.0.24 headless, PyAV 19.0.2, 13 runs, 20:06–20:12; scripts left in the session scratchpad: `vlc_rate.py`, `run_vlc.ps1`, `run_vlc2.ps1`; media deleted). Saved by the main session, which checked that no test process was left running. [M] = measured, [I] = inferred.

## Short answer

VLC plays a camera MKV at the **nominal (requested) rate**, not at true time. A camera MKV plays in true time only when the camera really delivered the nominal rate with no dropped frames. The `.mka` and the skellysync MKV play at the correct rate. A camera MKV and the `.mka` played together drift apart in proportion to the camera's real frame rate.

## Per case

| Case | Result |
|---|---|
| (a) Camera MKV alone | Nominal rate [M] (`results/sidecar_embedding/FINDINGS.md` §0–§1; desk test: 300 frames at 30 fps took 10.03–10.09 s). N s of capture plays as frames ÷ nominal fps [I]. |
| (b) `.mka` alone | Correct: 1,440,000/1,440,000 samples, offset 0, mono and stereo [M] (`flac_skau` FINDINGS §4). The live `.flac` loses its last 26.7 ms in VLC [M]. Microphone clocks are within about ±10 ppm of the host clock (≤ 36 ms/h) [M] (`audio_skellycam` §4.1). |
| (c) Camera MKV + `.mka` | Playable together with `--input-slave=<take>.audio.mka` (GUI: "Play another media synchronously"). On a matched synthetic pair: 0 samples error on 17/17 bursts; seeks ±8 ms [M]. On a real take they do not line up: both start at 0, the video runs at the nominal rate and the audio at true rate, and VLC's audio delay fixes only a constant offset [I]. `audio_skellycam` §4.5: "Never pair audio with index-pts video." |
| (d) skellysync MKV with FLAC | Correct rate and in step: 0..0 samples, seeks to the exact slot [M] (`audio_skellysync` §2); with one Cluster per frame also 0..0 on 17/17 bursts [M]. True rate only if skellysync takes a skellycam source's frame times from the sidecar (SFF-600, provisional) [I]. |
| (e) Rotation | Not a rate issue. VLC ignores MKV `Projection` and MJPEG rotation [M] (`rotation_flag` FINDINGS §0, §3); the format writes no container flag, so rotated cameras show in sensor orientation. |

## How wrong, and why

Measured delivered rates, 600 s at 720p30 (`research/usb_cameras/docs/windows_results_20261112.md` §1.2) [M]; playback length = frames ÷ 30 [I]:

| Camera | Delivered fps | VLC plays 600 s as | Error | Drift against true-rate audio |
|---|---|---|---|---|
| generic | 25.76 | 515.9 s | 14 % short | about 9.9 s per minute |
| Kiyo Pro | 29.38 | 587.5 s | 2.1 % short | about 1.3 s per minute |
| C930e | 30.05 | 601.4 s | 0.17 % long | about 0.1 s per minute |
| Kiyo Pro, 60 requested (delivers 30.02) | — | 2× speed if the nominal rate is written as 60 | 50 % short | — |

Causes: (1) the camera delivers less than requested (main cause); (2) dropped or lockstep-gated frames (lockstep at the generic camera's rate dropped 14 % of the C930e's frames, plan line 338) [M]; (3) the start offset between audio and video is not in either container (first frame 88–888 ms after session start; audio 9–74 ms after the anchor) [M]; (4) the 1 ms timestamp rounding is negligible and does not accumulate (SFF-104) [M/C]; (5) a writer that copies `stream.time_base` after the header stamps frames 1 ms apart and VLC drops 87 % of them (SE §1 pitfall) [M] — SFF-104 rules this out.

## One Cluster per frame (SFF-402)

Changes nothing for VLC [M]. With real-size JPEGs (640×360, about 28 KB) FFmpeg already writes one Cluster per frame (byte-identical size with and without `cluster_size_limit=1`, 300 Clusters). With small JPEGs (160×90) the limit adds about 15 B per extra Cluster (613,562 → 616,274 B); VLC played all four files with 0 late buffers and 0 Matroska errors, and a seek to 5 s landed on frame 150.

## Making VLC play at true rate

- **Real (VFR) container timestamps:** VLC would play true time, but OpenCV miscounts (888 for 891; 53,819 for 54,000), POS_FRAMES seeks miss with drops, frames < 1 ms apart share a timestamp, and recovered files report 62.5 fps [M] (`EVIDENCE_INDEX.md` GF02, line 110). Index timestamps gave exact OpenCV counts, 11/11 seeks and exact freemocap reads in all 18 files [M]. This is why the format uses index timestamps.
- **An "export for viewing" step:** copy the JPEG frames unchanged into a new MKV with timestamps from the sidecar, plus the audio shifted by the start offset and corrected by the fitted ppm. No re-encode; a second file that is not freemocap-exact.
- **Rewriting timestamps at finalisation:** needs a remux and breaks the offset/CRC invariants [I]. Not worth it.
- **Request a rate the camera delivers:** the exposure rule already requires delivered fps ≥ 0.99 × nominal; record the negotiated rate, not the requested one.

**Recommendation (sub-agent):** keep index timestamps in the camera MKVs (exact OpenCV and freemocap reads matter more than true time in VLC); state that camera MKVs are not for synchronised viewing in an external player; for external viewing with sound, use the skellysync MKV or a small "export for VLC" step; do not recommend `--input-slave` with raw camera MKV + `.mka`; put "delivered fps ≥ 0.99 × nominal" into the capture rules.

Not checked: a real VLC window (all runs used the dummy output), mpv or VLC 4, real camera files, VLC's automatic audio-file pairing.
