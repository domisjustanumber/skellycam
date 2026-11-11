# Windows results, Gerald, 2026-11-06

*2026-11-11: the next full run (2026-11-10/11) is written up in [windows_results_20261110.md](windows_results_20261110.md).*

Full results behind §9 of [xplat_capture_plan.md](xplat_capture_plan.md). Drafted from the verified run analyses (workflow `wf_6c2c6eb0-fee`) and reviewed before publishing. Section numbers here are 1–11; the plan's §9 summarises them.

**What was run.** `suite/windows` ran unattended twice on Gerald (Windows 11 build 26300) on 2026-11-06, with four cameras attached as found:
- C922 (046d:085c, serial key, tier-1 metadata on), behind the HS13 hub;
- generic 4c4a:4a55 (metadata off), on the same HS13 hub;
- C930e (046d:0843), alone on HS07. Its metadata value sits on a stale device instance, so it runs at tier 0 (flag in [R2 W-ENV]);
- Kiyo Pro (1532:0e05, SuperSpeed on the Thunderbolt xHCI, metadata on).

The two runs:
- **Run 1 (R1)** started 13:19 local and covered **all modes**. The Kiyo was already wedged when it first streamed.
- About 30 harness fixes then came out of R1's verified analysis. The mode scope (plan §6: streaming tests only at ≥ 30 fps and ≥ 720 lines) and W-FMT-NOGRAB were added.
- **Run 2 (R2)** ran 17:49–19:13 local (22:49Z–00:13Z, 1 h 24 min, [R2 summary]). Dom had replugged the Kiyo at 15:32 local.

Each run's results were analysed per test group and checked by an adversarial verifier (R1 and R2 `analysis/*.md`). This section uses those findings only as the verifiers corrected them. Numbers come from R2 unless marked R1. Labels: *measured* (a result file and field support it) and *inferred* (reasoning).

**Bottom line.**
- **MF native should be the primary capture path on Windows.**
  - Its open/close reliability equals DirectShow's: 360/360 cycles each in R2, and 630/630 each over both runs on the healthy cameras.
  - It always delivered the requested MJPEG.
  - It reaches the first frame 260–290 ms sooner than DirectShow.
  - It gives a bandwidth refusal as a certain HRESULT.
  - It is the only path to tier-1 device timestamps.
- **DirectShow is a usable fallback only through the ffmpeg CLI (`-vcodec mjpeg`).** PyAV silently falls back to YUY2 whenever a raw format matches the requested size and rate.
- **OpenCV `CAP_DSHOW` is not a candidate.** skellycam's real open sequence opens 120/120 times, but its first configured frame takes 2.7–11.5 s.
- **G-TS:** no tier-0 route can reach G-TS yet, and tier 1 is self-consistent only on the C922. The ground-truth rig (A5) is still the deciding measurement.
- **Kiyo:** it wedged again 210.6 min after plug-in. In R1 the wedge fell between 200.6 and 224.3 min.
  *(2026-11-11: on 11-10/11 it wedged at about 4–5 min and at 525.2 min after plug-in, so the plug-in-age pattern
  does not hold. See [windows_results_20261110.md](windows_results_20261110.md) §9.)*

## 1. Formats and controls: MF vs DirectShow, and listing without grabbing

**MF and DirectShow list the same formats on every camera** (*measured*, [R2 W-FMT] `measurements.cameras[*].counts`, `diff.mf_vs_ds` empty on all four; rating `fmt_equivalence` yes):

| Camera | Descriptor modes | MF native | DS capture | MJPEG modes (sizes), descriptors = MF = DS | NV12 types synthesized by MF |
| --- | --- | --- | --- | --- | --- |
| C922 | 218 | 218 | 218 | 120 (17) | 120 |
| Kiyo | 112 | 112 | 112 | 28 (4) | 0 |
| generic | 14 (+5 still) | 14 (+5 still) | 14 (+5 still) | 10 (5) | 13 |
| C930e | 218 | 454 | 454 | 119 (17) | 119 |

- **C930e H.264.** The C930e's extra 238 MF/DS entries are 119 size/rate modes, each listed under two subtypes (`H264` and `MFVIDEOFORMAT_H264_ES`). They come from its second, non-standard pin. DirectShow now parses them through `H264VI` (`ds_pins.1.header_kinds`). In R1 they read as 14 modes of size 0x0, a harness gap that fix H7 closed (*measured*).
- **Two C930e modes reach no Windows API.** YUY2 2304x1296@2 and 2304x1536@2 are in the descriptors but missing from MF, DirectShow and ffmpeg (*measured*, [R2 W-FMT] `diff.mf/ds`, [R2 W-FMT-NOGRAB]).
  - The R1 explanation (`dwMaxBitRate` above the High-Speed isochronous maximum) is **refuted**. The C922 has byte-identical descriptors for both modes (`dwMaxBitRate` 238.9 and 283.1 Mbit/s), and MF, DirectShow and ffmpeg all list them on the C922 ([R2 descriptors] bFrameIndex 18/19; W-FMT C922 `mf_missing` []).
  - So the gap is specific to the C930e. Its cause is unknown (*inferred*).
- **Trap 1 is unchanged.** MF still inserts a decoded NV12 type before every MJPG type on the three cameras that have no native NV12 (table above, *measured*).

**Controls: identical through MF and DirectShow on all four cameras** (*measured*, [R2 W-CTRL-LIST] `verdicts.ctrl_list_equivalence`):
- Supported controls: C922 16, Kiyo 16, generic 11, C930e 16.
- Against the descriptors, 0 are missing on either API, there are 0 MF-vs-DS differences, and `iam_ks_disagree` is empty.
- R1's untested G-CTRL row is gone.

**FMT-NOGRAB: which method lists formats without grabbing the camera** (*measured*, [R2 W-FMT-NOGRAB] `results.<method>.<camera>`; three conditions: idle, camera streaming in another process via MF, and via DirectShow):

| Method | Complete vs descriptors | Works while another process streams | Disturbs that stream | Opens a pipe / changes alt | Delays another process's open | Time |
| --- | --- | --- | --- | --- | --- | --- |
| Hub IOCTL descriptor read | 4/4 exact, **by construction**: the reference is the W-FMT hub-IOCTL cache (`reference.source`, `w_fmt_nograb.py:437`) | yes | no | no | not shown: in 6 of 8 runs the method ended before the other open's first frame | 70–87 ms, 5–8 EP0 requests |
| MF `ActivateObject` + `GetNativeMediaType`, no `Start` (source held 2.5 s) | 3/4. C930e 97/99: only the 2 YUY2 modes that no API exposes | yes | no | no (alt 0, `active` false) | no (−24 to −8 ms vs control) | 29–61 ms incl. process start |
| DirectShow bound filter + `IAMStreamConfig` + `GetFrameRateList` (held 2.5 s) | 3/4, same C930e gap | yes | no | no | no (−3 to +1 ms) | similar to MF |
| `ffmpeg -list_options` | 1/4. It prints only the minimum and maximum rate per caps entry: C922 MJPEG 34/120, Kiyo 8/28, C930e 34/119; the generic is complete | yes | no | no | not shown | – |
| OpenCV, WinRT | not run. Rated "no" by assertion (`w_fmt_nograb.py:55-61`), as the plan's "noted" allows | – | – | – | – | – |

- **Disturbance** (*measured*, `disturbance.window_max_interval_ms`, `pipe_change.changed` false): no method disturbed another stream. The largest frame interval was 49.04 ms at 30 fps (65.3 ms on the generic at 17 fps), equal to the baseline 16 ms grid jitter, and the alt never changed.
  - The pipe sampler was validated by positive controls: it saw the streaming camera's pipe on every camera, and the blocker's pipe in the idle condition.
  - Caveat: blocker exclusion dropped part of the 2.5 s idle hold, so "no pipe opened" covers only 36–64% of the hold (24% on the Kiyo).
- **ffmpeg misses the default mode** (*measured*, `raw/W-FMT-NOGRAB/*/idle/ffmpeg_main.err`). On the C922 and the Kiyo, 1280x720 prints as `fps=5 … fps=60.0002`, so a UI built on ffmpeg's listing would never offer 720p30 MJPEG.
- **A concurrent MF open slows the hub IOCTL** from 78–84 ms to 208–511 ms on the C922, C930e and Kiyo; the generic stayed at 74 ms (*measured*, raw `session.json` blocking runs). Probable cause: EP0 requests queue behind usbvideo's stream-start control transfers (*inferred*).
- **The Kiyo** passed all of W-FMT and W-FMT-NOGRAB at plug-in ages of 137–140 min (*measured*).

**Answer.** For the list a user sees, use MF activation with `GetNativeMediaType` and no `Start`. It is complete for every mode Windows can open, works while another process streams the camera, and grabs nothing (*measured*). Use the hub IOCTL for descriptor-level data: `dwMaxBitRate`, alt tables and the mode-alt cache. It also shows modes that Windows cannot open (C930e 2304-wide YUY2) and misses extension-unit formats (C930e H.264) (*measured*).

## 2. Reliability: open/close with MF, DirectShow and OpenCV

**R2 ran 1,080 cycles and every one opened, delivered a first frame and closed** (*measured*, [R2 W-CYC] `variants.*.summary`: `n_ok` = `n`, hangs 0, unreleasable 0, `device_reset_count` 0, `arrivals.changes` []):
- per camera: 90 MF, 90 DirectShow (PyAV) and 30 OpenCV cycles;
- ratings: 21 yes, 3 partial (format mismatch), 8 no (latency).

Open to first frame, p50 in ms (*measured*, `variants.<v>.summary.open_to_first_frame_ms_p50`; close from `timings_ms.close_ms.p50`):

| Camera | MF in-process / new process / mode switch | DS (PyAV) in-process / new / switch | OpenCV, create-step sets only | OpenCV, skellycam's full sequence | Close, all APIs |
| --- | --- | --- | --- | --- | --- |
| C922 | 327 / 330 / 331 | 593 / 616 / 591 | 3047 | 4758 | 332–356 |
| Kiyo | 910 / 914 / 918 | 821 / 855 / 827 (YUY2) | 7449 | 11497 | 913–1117 |
| generic | 98 / 100 / 111 | 392 / 414 / 392 | 2086 | 2705 | 263–270 |
| C930e | 511 / 515 / 513 | 773 / 808 / 787 | 4245 | 6388 | 340–388 |

**MF vs DirectShow, by Dom's criterion: equally reliable** (*measured*, `summary.n_ok`; Wilson bounds computed by the analysts):
- R2: 360/360 cycles per API (pooled Wilson lower bound 0.989).
- R1 + R2 on the healthy cameras: 630/630 per API (lower bound 0.994).
- Per-cell lower bounds are only 0.796–0.929. A per-camera "≥ 99%" claim needs at least 381 failure-free cycles (*inferred*).

**Where they differ** (*measured*):
- **Latency.** MF reaches the first frame 266, 294 and 262 ms sooner on the C922, generic and C930e. In R1 the gaps were 256, 272 and 290 ms. All p50s match R1 within 30 ms ([R1 W-CYC]).
- **Format integrity.** MF negotiated MJPG in 360/360 cycles. PyAV-DS delivered MJPEG in 270/360 (`format_mismatch_count`).
  - All 90 misses were on the Kiyo: YUY2 at 22.4 fps (`codec` rawvideo, `format_fallback` true). PyAV cannot force `vcodec=mjpeg` when a raw caps entry matches.
  - The figure depends on the mode scope. In R1, the 640x480@30 mode-switch partner also fell back on both Logitech cameras.
- **The Kiyo DS "partial" cells come from the harness's format check.** The plan's §3 reliability row has no format criterion, so read literally they would be "yes" (*inferred*).
- **Close time** follows the camera, not the API. The Kiyo needs about 1 s on every API, quantised in roughly 100 ms steps on MF, DirectShow and OpenCV alike. Inferred: a camera or driver-side poll.
- **Vendor software.** RazerAppEngine (pid 37240) held the Kiyo, without streaming, during all 75 in-process MF cycles, and every cycle succeeded (`activity_pids`). Attachment alone does not break streaming (*measured*).

**OpenCV `CAP_DSHOW`, with skellycam's real sequence** (`opencv_skellycam`, *measured* from rows `sets`, `apply`, `final`):
- skellycam opens in two steps:
  - create step: FOURCC, W, H, FPS, `BUFFERSIZE`=1, then `read()`;
  - apply step: exposure, W, H, then FOURCC last.
- After the create step alone, the C922 and C930e are in **YUY2 at 10 fps** and the Kiyo in YUY2 at 22.6 fps. The apply step then ends in **MJPG 1280x720** at 30.0, 30.2 and 29.8 fps (generic 25.7).
- Time from `VideoCapture()` to the first configured frame: generic 2.71 s, C922 4.76 s, C930e 6.39 s, Kiyo 11.50 s. 0 of 60 cycles came within 2 s. The property sets dominate (create 1.7–6.5 s, apply 0.56–3.5 s).
- `CAP_PROP_BUFFERSIZE=1` is refused on all four cameras (`sets.buffersize` False, `got_buffersize` −1). skellycam's own comments claim DSHOW honours it (`create_cv2_video_capture.py:27`, `determine_backend.py:39`).
- Manual exposure −7:
  - On the C930e it read back −5 in 14 of 15 cycles.
  - On the generic the readback cannot prove the set took, because the auto value was already −7. Only the change in fps suggests it did.
  - The restore step resets only the auto flag, so the C922 and Kiyo were left at value −7 (originally −4).
- Caveat: the harness passed framerate 30. skellycam's default framerate is −1 (`camera_config.py:26`), which skips the FPS set, so the measured latency is probably slightly pessimistic (*inferred*, harness bug below).

**R1 → R2.**
- *Fixes and scope:*
  - `ds_modeswitch` on the C922 and C930e went from partial (R1 reanalysis) to yes only because the scope replaced the 640x480 partner, which fell back to YUY2, with 1080p30.
  - `opencv_skellycam` is new.
- *Cameras:*
  - The Kiyo was alive (3 yes, 3 partial, 2 no).
  - The generic's `opencv_inproc` cell lost R1's two 11.35 s set / YUY2 640x480 cycles, one of which coincided with a re-arrival. The generic is not a clean camera, though: it re-arrived at 18:17:09Z and 22:26:45Z, before each run.

## 3. Native MJPEG

**In scope (R2): 9 of 12 cells yes. The 3 Kiyo cells are untested because of the device fault** (*measured*, [R2 W-MJPEG] `verdicts`, `measurements.cameras[*].modes[].apis.{mf,pyav_ds}`):

| Camera | In-scope modes | MF and PyAV-DS | fps delivered (reference) | Requested rate honoured |
| --- | --- | --- | --- | --- |
| C922 | 1280x720@30, 960x720@30, 1280x720@60, 1600x896@30, 1920x1080@30 | MJPG with verified readback; SOI/EOI/SOF0 1.0; strict decode 1.0 | @60 delivers 30.55; the UVC PTS gives the same rate (`fps_reference` 30.5545, `uvc_pts`) | 4/5 |
| C930e | 1280x720@30, 1600x896@30, 1920x1080@30 | same | 30.02, 29.94, 30.04 (both APIs agree) | 3/3 |
| generic | 1280x720@30, 1920x1080@30 | same; 1080p strict 0.0 / lenient 1.0 (known "extraneous bytes before EOI" quirk) | 17.15 on both APIs at @30 | 0/2 |
| Kiyo | 1280x720@30/60, 1920x1080@30/60 | gated: faulted in W-MULTI; the re-probe failed with 0x8007001F at `first_sample` | – | – |

What this shows (*measured* unless marked):
- **MF and DirectShow deliver the same bytes.** The header SHA-1 is equal across MF and PyAV-DS in 10/10 modes. It is also identical to R1's in all 10, so JPEG headers are deterministic per camera and size.
- **The ffmpeg CLI was never needed in R2.** PyAV got MJPEG in every in-scope mode on these three cameras (`pyav_format_fallback_modes` []).
- **CPU** on the 10 s default mode: MF 2.49% (C922), 1.72% (C930e), 0.94% (generic); PyAV 1.25%, 1.87%, 0.78% of one core (`cpu_pct_one_core`).
  - The 3 s modes have 0.52% resolution.
  - MF and PyAV measure different process scopes, and neither includes Frame Server.
- **Open to first frame:** MF 298–333 ms (C922), 498–515 (C930e), 83–99 (generic); PyAV 596–620, 803–814, 397–401 (`timings.open_to_first_frame_ms`), as in R1.
- **The C922 at 720p60 runs at 30 fps.** The device clock agrees, so the camera is the cause, not the host. `auto_exposure_priority` was 1 before and after (`control_state`).
  - usbvideo still reserves alt 11 for this mode ([R2 mode_alt_cache]), and the C922 uses 9.2% of it (`bus_utilisation_top`).
  - **No in-scope 60 fps stream was verified at 60 fps in R2.**
- **Bus load.** C922 bus utilisation in every in-scope mode is at most 0.21 of the reservation, so R1's @5 overrun mechanism (below) cannot occur at ≥ 30 fps.
  - Only the C922 yields bus data. The generic and C930e have no metadata. The Kiyo reports `uvc_scr_sof` = 0 on every frame even with metadata on.
- **The generic's "yes" hides 57% of the requested rate.** The camera delivers 17.15 fps at @30. On tier-0 cameras the fps reference is the mean of MF and DS when they agree within 2% (`rating.py:207-222`), so the criterion cannot fail. The C930e and generic cells therefore show only that the two APIs agree.
  - The generic was already at 17.15 fps in the W-FMT-NOGRAB streamers at 22:51Z ([R2 W-FMT-NOGRAB] `streamer_runs[0].summary.fps_measured`). In R1 (daytime) it ran 25.7.
  - With manual exposure −7 through OpenCV, it reached 25.7 in R2 ([R2 W-CYC] `opencv_skellycam.final.fps_measured_p50`).
  - *Inferred:* auto exposure in evening light, capped at about 25.7 fps even in daylight. It never reaches 27 fps (0.9 × 30), so it would be flagged in both runs once MF/DS fps are judged.
- **Kiyo MJPEG works through MF at 720p30**, outside the rated test. In W-FMT-NOGRAB its MF streamer delivered 349 valid MJPEG frames at 30.00 fps, and in W-CYC it ran 90/90 MF cycles at about 29.7 fps. Its PyAV-DS streamer fell back to `yuyv422`, which reconfirms REPORT finding 2.
  - The Kiyo's MJPEG modes, including its 60 fps modes, remain **unrated in both runs**: R1 faulted before them, and R2 gated them at about 218 min after plug-in.

**All modes: R1 only. R2 did not re-measure these** (R1 [R1 a-mjpeg] with verifier corrections, from [R1 W-MJPEG]):
- **MF across all modes** (*measured*): MF negotiated MJPG with a verified readback in **249/249** advertised modes on the three working cameras. SOF0 matched on 100% of frames, and the header SHA-1 equalled DirectShow's in 249/249.
- **C922 below 30 fps** (*measured*): its MJPEG path ignores frame intervals below 30 fps. 100 sub-30 modes deliver about 30 fps, while YUY2 in the same session follows the request (6.00, 7.50, 10.0, 15.0).
  - The verifier refuted auto-exposure priority as the cause, since priority can only lower the rate.
  - *Inferred:* MJPEG firmware behaviour.
- **Torn C922 frames at @5:** 1280x720@5 and 1600x896@5 deliver 15 fps with torn frames (EOI on 84.8%) on both MF and DS (*measured*).
  - The bus time per frame (`uvc_scr_sof`, `uvc_eof_scr_sof`) multiplied by the 30 fps actually sent fills 96% and 99% of the reservation usbvideo sized for 5 fps.
  - *Inferred:* a predictable overrun, not random corruption. For skellycam: request 30 fps and decimate on the host.
- **C930e rate drift** (*measured*): MJPEG speeds up in 9–10 modes (+2.4% to +14.6%, in bursts), while YUY2 holds the requested rate. The generic runs 25.7 fps at both @25 and @30.
- **PyAV fallback** (*measured*): PyAV fell back to YUY2 in 95/120 (C922) and 96/119 (C930e) modes. Whether it does depends on the caps order. The ffmpeg CLI with `-vcodec mjpeg` delivered MJPEG with MF's header bytes in every one of those modes.
- **Re-rated with the symmetric fps reference:** MF partial on the C922 (118/120, the 2 torn modes) and on the C930e (113/119), yes on the generic. PyAV partial (25/120, 22/119).

**Answer.** Native MJPEG at every resolution works on Windows through MF, and through DirectShow via the ffmpeg CLI (*measured*, R1 all modes; R2 in scope). The failures are camera behaviour: rates that are not honoured, and C922 tearing at @5. PyAV alone is not enough.

## 4. Timestamps: tier 0 vs tier 1

R2 rated 28 G-TS cells: 3 partial, 8 no and 17 untested (*measured*, [R2 W-TS] `verdicts`; [R2 suite_log] line 952). An offline re-analysis with the current code reproduces every rating ([R2 a-ts], verifier). The 17 untested cells break down as:
- 8 frame-index cells, untested by design because there is no ground truth;
- 6 aggregates in which the untested frame-index route outranks a measured "no";
- 3 Kiyo device-clock cells (2 routes plus their aggregate).

| Route | Tier | C922 | Kiyo | generic | C930e |
| --- | --- | --- | --- | --- | --- |
| MF sample time, MF QPC arrival, DS arrival | 0 | **no**: exact 16.0 ms grid | **no** (16.0 ms) | **no** (16.0 ms) | **no** (16.0 ms) |
| DS `pyav_pts` | 0 | **no**: synthesized, 33.3333 ms counter | **no**: 33.3383 ms counter (YUY2 fallback capture) | **no**: 33.3383 ms counter | **no**: 33.3333 ms with 18 corrections |
| Frame-index fit to arrival | 0 | untested; residual 4.61 ms | untested; 5.01 ms (start-up transient) | untested; 4.63 ms | untested; 4.66 ms |
| UVC PTS | 1 | **partial**: 300 MHz, −7.06 ppm, step std 0.289 ms, monotonic | untested: a 1 kHz counter (fit 1000.075 Hz) against a 30 MHz `dwClockFrequency` | n/a (no metadata) | n/a (no metadata; stale instance) |
| UVC SCR STC | 1 | **partial**: 2.2 µs residual, −7.51 ppm | untested: 30 MHz units that move in 1 ms steps; residual 1.66 ms | n/a | n/a |

Sources: [R2 W-TS] `apis.mf.grid_sample_time`, `apis.ds.pts_synthesized`, `frame_index_fit_arrival.causal.residual_stats_ms`, `apis.mf.pts_units`, `pts_vs_sequence`, `uvc_scr.vs_sequence`, `uvc_scr.units`. All *measured*.

**Tier 0** (*measured*):
- **Every host timestamp sits on an exact 16 ms grid.** This holds for MF sample time, MF QPC arrival and DS arrival, including the SuperSpeed Kiyo on the Thunderbolt controller.
- **The frame-index residuals equal the quantisation floor.** They are 4.58–4.66 ms on the regular cameras, which is 16/√12. So the fit's real error against capture time cannot be seen without a ground truth.
- **DS pts are synthesized on every camera.** The C930e's DS pts jumped 56.37 ms at a real 65 ms gap, so a drop is partly visible in them.
- **A cheap tier-0 detector.** The residual variance above the grid floor, √(var − 16²/12), gives: C922 0.00, generic 0.14, C930e 0.475 and Kiyo 1.645 ms (offline, [R2 a-ts]). It detects host-visible delivery jitter, so it flags cameras on which a constant-period model will fail.
- **R1 → R2:** fix B2 made the frame-index slotting correct. The generic and C930e DS residuals fell from 9.4–9.7 ms (phantom slots) to 4.58–4.66 ms.

**Tier 1** (*measured* unless marked):
- **The tier split is exact.** The C922 and Kiyo (metadata on) carry PTS, STC and SOF in 901 and 902 MF frames. The generic and C930e carry none (`apis.mf.fields`). This is the first full run with Kiyo tier-1 data.
- **C922.**
  - **STC:** a 2.2 µs-regular first-payload frame clock.
  - **PTS:** its 0.145 ms residual is a deterministic even/odd alternation between steps of about 33.04 ms and 33.63 ms (lag-1 autocorrelation −0.999), not random jitter.
  - **Drops:** 0, detected by PTS.
  - **SOF:** advances 884/s instead of 1000/s (`uvc_scr.sof.counts_per_s`), the Linux `UVC_QUIRK_INVALID_DEVICE_SOF` behaviour, which the new SOF check flags. Transfer-time figures counted in SOF units are therefore approximate.
- **Kiyo** (streamed at plug-in ages of 199.7–200.8 min).
  - **PTS:** ticks at 1 kHz, with steps of 27–43 ticks. The STC uses 30 MHz units but moves in 1 ms steps. SOF is always 0. The EOF SCR equals the first-payload SCR, so no transfer time can be measured.
  - **One oscillator:** PTS and STC share it (fitted ratio 30000.115, offline).
  - **PTS against host timing:** std(sample time − PTS) = 4.613 ms, which is the 4.619 ms quantisation floor (a shifted control gives 5.27 ms; offline, [R2 a-ts] verifier). So the PTS explains all host-visible timing beyond quantisation.
  - **Open question:** is the exposure cadence irregular, or is the PTS latched at a jittery delivery event? The PTS residual's lag-1 autocorrelation of −0.32 fits either reading. Only the rig can decide (*inferred*).
  - **Drops:** sample-time drop counting reports 32 phantom duplicates on the Kiyo, while PTS reports 0.
- **R1 → R2:**
  - The C930e `ds:pyav_pts` cell went from untested to no (fix B3).
  - The C922 PTS alternation amplitude fell from 0.347 to 0.145 ms, and the C930e DS pts corrections fell from 327 to 18. The corrections change is a shift in the DS graph's correction onset, not a camera change.
  - Both runs are confounded by time of day: W-TS ran at 14:45 local in R1 and 18:51 in R2, after W-CTRL-EFFECT (*inferred*).

**Answer.**
- At tier 0 on Windows, every native stamp is a 16 ms host grid or a synthesized counter. The only remaining tier-0 candidate is a frame-index fit, and its accuracy cannot be scored without the rig (*measured*).
- Tier 1 adds a self-consistent device clock on the C922 only.
- The Kiyo's PTS is non-standard (1 kHz). It tracks host-visible timing, but whether it marks exposure is unknown.
- A tier-1 implementation needs per-camera validation of the clock's units, step regularity and SOF rate (*measured*: three different behaviours on two cameras).

## 5. Controls

**Effect in the image, both paths, 3 runs per control** (*measured*, [R2 W-CTRL-EFFECT] `cameras[*].paths.{mf,ds}.controls.*.runs[*]`, `persistence`, `restore`):

| Camera | Rating MF / DS | Exposure | Gain | WB | Focus (AF off) | Before and after stream start |
| --- | --- | --- | --- | --- | --- | --- |
| C922 | yes / yes | luma ×17.7–18.2 | ×2.83–2.86 | R/B ×2.74–2.78 | sharpness ×57.8–58.6 | holds, persists |
| Kiyo (plug-in age 188–192 min) | partial / partial | ×3.6–3.7 | after start ×1.004–1.012, below the 1.075 needed (26→128 adds 20% luma, 128→230 adds 1%) | ×2.2 | ×10.7–11.3 (MF JPEG); ×7.9–8.2 (DS raw YUY2) | everything holds and persists |
| generic | partial / partial | ×9.3 | no effect (×0.985–1.0); **reverts to 4 at every stream start** | no effect (×0.97–1.0) | – | gain does not hold |
| C930e | partial / partial | sets made 1 s or more after the first frame work | sets made 1 s or more after the first frame work | holds | holds | **exposure resets to −5 (still flagged manual) at 14/14 starts; gain jumps to 49–51 at 8/8** |

- **MF and DirectShow behave the same.** The same reverts happen on both paths, and luma and WB metrics agree within about 2%.
  - Sharpness does not agree: the Kiyo's DS raw-YUY2 frames read about 27% lower than its MF JPEG frames, so the raw path is not validated for focus (*measured*).
- **The Kiyo gain response is compressed, cause unresolved.** No pixels clip (0% ≥ 250). The Kiyo's non-default brightness 205, contrast 201 and backlight compensation 1 suggest an ISP tone curve (*inferred*).
- **The C930e's post-start gain follows its auto-exposure gain:** 14–18 in R1 (daytime), 49–51 in R2 (evening). Only the value 26 was set. *Inferred:* the camera re-runs AE at stream start.
- **Restore is clean on all 8 paths.** The check compares flags, not values.
- **These persisted across Dom's replug** (*measured*, [R2 W-CTRL-LIST] vs [R1 W-CTRL-LIST]): the Kiyo's non-default brightness, contrast, saturation and backlight, and the generic's non-default values across its re-arrivals. Whether the camera stores them or vendor software re-applies them is unknown (*inferred*).
- **R1 → R2:** the Kiyo was measured for the first time (in R1 it was dead by this test, at 291 min). Fixes V1 and B3–B5 removed R1's carry-over artefacts: the C930e WB after-start ratio is 1.105–1.114 (R1: 1.053).

**Answer.** Both paths reach the same controls, ranges and effects (*measured*). Two practical rules follow:
- apply controls after the first frame, and verify them on the image (C930e);
- keep a per-camera capability table: on the generic, gain and WB are unusable (*measured*).

Gain and focus are the weak spots. No camera passed every control without a workaround except the C922.

## 6. Identity

- **Mapping and stability** (*measured*, [R2 W-ID] `verdicts["G-ID"]`, `timing_ms`): six enumeration APIs map 1:1 to `camera_identity` keys, with identical order over 20 runs: MF, DirectShow, PyAV dshow, ffmpeg CLI dshow, OpenCV MSMF and OpenCV DSHOW. The indices are the same as in R1. `key_source_stability` is yes.
- **Enumeration p50:** MF 2.19 ms, DS 4.81 ms, OpenCV 2.2–3.0 ms, PyAV 157 ms, ffmpeg 219 ms.
- **G-ID is partial (provisional).** Reboot and same-port replug are null: they are attended item A1, which was not run.
  - `port_move_serial` is true. It comes from the 10-27 comparison, in which the serial-keyed C922 moved port and kept its key (`persistence_inputs`).
- **Only the C922 has a serial key.** The other three are port-keyed (`discovery.json`).
- **Natural replug evidence.** The Kiyo (a real replug) and the generic (re-arrivals) kept key, instance and symlink from R1 to R2 ([R1 discovery], [R2 discovery], `run_suite.json` `arrivals_since_previous_run`). The rating does not use this yet (*measured*; harness gap).

## 7. Bandwidth, the topology mapper, and the user message

**Every over-budget pair on HS13 was refused, on every API: 63/63** (*measured*, [R2 W-MULTI] `summary_by_api`: 21 refusals per API, `false_over` 0, `false_fits` 0):

| Scenario (load as % of one microframe) | MF | DS (ffmpeg CLI, `-vcodec mjpeg`) | PyAV |
| --- | --- | --- | --- |
| All 4 cameras together at 720p30; HS13 pair at 81.1% (×10) | 10/10 refused; C922 lost 10/10 | 10/10 refused | 10/10 refused (DS + PyAV losers: C922 13, generic 7) |
| Staggered 2.5 s steps (×5) | 5/5; the generic, opened last, lost | 5/5, generic lost | 5/5, generic lost |
| Pairs: C922 1080p30 or 720p60 + generic (98.4%) | refused | refused | refused |
| Pair: C922 960x720@30 + generic (93.97 µs = 75.2%, model "marginal") | 2/2 streamed | 2/2 | 2/2 |
| C930e on HS07 alongside the generic (98.6%, different root ports) | streamed in all of the C930e's 45 runs | | |

- **Predicted cost matched the observed open pipe in 149/149 observations** (*measured*, `predicted_vs_observed`, `learned_costs`): 148 streaming cameras plus the hung Kiyo.
  - First observations: C922 720p60 at alt 11 (61.41 µs), C922 960x720@30 at alt 8 (32.39 µs), Kiyo SS alt 1 (6.32 µs).
  - The 960x720 pass reproduces the 10-27 pass edge (≤ 75.2%).
- **How each API reports the refusal** (*measured*):
  - **MF:** `0x800718CF` at the first `ReadSample` in 21/21 refusals (`bandwidth_certain`). The loser is deterministic: the C922 lost every simultaneous run, because the generic's first frame came at 56–216 ms.
  - **DirectShow and PyAV:** `OSError(5)`/EIO, classed `bandwidth_probable`, which is why their cells are partial. The FFmpeg log separates the cases. "Could not run graph" appeared in 42/42 HS13 refusals and "Could not RenderStream" in 16/16 Kiyo not-ready failures. PyAV logs are now captured (36/36; R1: 0/36).
  - **Open duration does not separate them.** The wedged Kiyo's failures (509–748 ms) overlap the generic's refusals (510–713 ms).
- **The generic re-enumerates 10.03–10.11 s after 18 of its 25 DirectShow-family refusals**, and never after its 5 MF refusals. The C922 never re-enumerated after any of its 33 refusals (*measured*, `timeline`, `arrival_attribution`). In R1, one re-arrival came about 24.6 s after a refusal.
  - 0 HS13 events were contaminated by `device_not_ready` (R1: 5), thanks to the settle wait.
- **Retry after a refusal works on both APIs** (*measured*, `events.*[*].retry`):
  - MF: 6/6 on the first try.
  - DirectShow family: 19/19 on the final try and 18/19 on the first. The one failure was the generic's first refusal, before the harness knew that it re-enumerates.
  - No zero-frame start was seen.
  - The retries cover only 6, 9 and 10 of each API's 21 refusals, and each one reopens the loser alone.
- **Cost of the waits.** Settle waits (98.2 s) and retry waits (67.1 s) grew W-MULTI from 650 s to 940 s. Six waits ran to the 25 s timeout and cost 16.0–19.5 s each (*measured*).

**The mapper (W-TOPO): yes** (*measured*, [R2 W-TOPO] `verdicts.mapper`):
- no admin, 0 device requests, 0.054 s;
- a domain for every camera, and alt tables for all four;
- the 10-27 pairs agree (81.1% over; 59.7% and 62.2% fit);
- 0 suggested ports in the conflict domain.

The W-TOPO G-BW cell is "untested" by design: TOPO only predicts.

**Example user message, verbatim** (R2, run `mf_all_together_001`, [R2 W-MULTI] `measurements.messages[0].message`):

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

On DirectShow the second line reads `…failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).`

What the messages got right and wrong (*measured*, `messages[*]`):
- **Right:**
  - 63 messages, 11 distinct texts, 0 null (R1 had 5 null).
  - The port list never names HS13 or HS07, as plan §5 requires, and puts the strong-evidence ports first.
- **Wrong:**
  - The staggered messages say "2.5 s apart". The generic actually started 5.0 s after the C922, because the Kiyo opened in between.
  - The stay-here advice for the 720p30 and 1080p30 conflicts drops to 640x480@30, although 960x720@30 measurably fits. The cause is the model's 93.75 µs "fits" limit (`topology_model.py:60`).
  - For the 720p60 conflicts it offers 1080p@5, a 12× frame-rate drop.

**R1 → R2.**
- *Fixes:* ds and pyav_ds went from no to partial, and the mapper from partial to yes.
- *Wait policy:* the settle and re-arrival waits removed the contaminated events.
- *Mode scope:* R1's YUY2 false fits are gone.
- *Not tested in R2:* the "fits" side on HS13. In R1, 640x480@30 + generic (59.7%) and 1080p@5 + generic (62.2%) streamed 2/2 on MF. On PyAV they were refused 0/2 because PyAV fell back to YUY2, which raised the real load to 92.6% and 98.4% ([R1 a-multi]).

## 8. Kiyo Pro

**Onset in both runs** (*measured* unless marked):

| | Run 1 | Run 2 |
| --- | --- | --- |
| Plug-in | 14:59:24Z (09:59 local) | 20:32:29Z (15:32 local, Dom's replug) |
| Healthy work before onset | quick self-test streamed at 171–200 min; W-FMT and W-CTRL-LIST normal at about 200.6 min | W-FMT/FMT-NOGRAB 137–140 min; W-CYC 210 cycles at 148.8–164.3 min; W-CTRL-EFFECT 188–192; W-TS 199.7–200.8; W-MULTI 28/28 streams, the last ending 00:02:59.95Z (210.51 min) |
| First symptom | 224.3 min: first full-run stream (MF 640x360@5). One frame at 2170 ms, then `reader_release` hung for more than 5 s | 210.58 min: DS (ffmpeg CLI) MJPG 720p30 open in `ds_staggered_037` hung for 35.27 s; ffmpeg used 98% of one core, and the iso pipe was open at alt 1 |
| Then | `0x8007001F` at `first_sample` (MF) and OSError 5 (DS) on every call | MF and DS control queries timed out at 3 s (00:03:39–45Z) → `ds_staggered_038` failed with RenderStream in 3.1 s (00:03:50.7Z) → first `0x8007001F` KS GET at 00:04:01.9Z, on 15/15 device-backed controls (suite fault record 00:04:02.35Z, 211.6 min) |
| Onset window | 200.6–224.3 min (untouched 13:19:59–13:43:39 local) | 210.51–210.58 min |
| Device state afterwards | no re-arrival, problem code 0 | no re-arrival through 00:13:20Z; the W-MJPEG re-probe (about 00:11Z) failed with `0x8007001F` at `first_sample` |

Sources:
- R2: [R2 W-MULTI] `runs[35..36].cameras[1]`; raw `W-MULTI/ds_staggered_036/_037` summaries (`utc_started`, `open_duration_ms` 35271.8, `process_cpu_s` 29.5 over a `lifetime_s` of 30.0); [R2 W-KIYO] `polls`, `failure_codes`; [R2 run_suite] `faults`; [R2 W-MJPEG] `device_faults.probes_by_test`.
- R1: [R1 a-cyc] §4 and verifier notes.

**The same signature in both runs** (*measured*):
1. A stream start hangs: the MF reader release in R1, the DirectShow graph open in R2.
2. Every call then fails fast with `0x8007001F`. The devnode stays healthy, with no re-arrival.
3. Only a replug recovers it.

The suite's own onset record is wrong by 38–61 s (*measured*):
- `summary.md` gives "first unanswered poll 00:03:01.219". That stamp was taken before a 38 s camera-lock wait; the query actually ran at 00:03:39.45 (wincam `utc_started`).
- `run_suite.json` gives 00:04:02 `control_get`, which misses the 00:03:03.9 hang.
- The DS onset age in `summary.md` (210.5 min) should read 211.2 min.

**Run 3: control run, polls only, 2026-11-06/07** (*measured*, [kiyo_overnight_20261106/README.md](../results/windows/Gerald/kiyo_overnight_20261106/README.md)):
- **Setup:** fresh replug at 00:50:01Z, same port, same power settings (LPM Moderate, selective suspend on), and the same vendor apps holding the camera. Only read-only MF and DS control polls ran, every 10 s from 4.7 to 304.7 min of plug-in age, with no streaming and no other camera work.
- **Polls:** 1801/1801 MF and 1801/1801 DS answered, 16/16 controls each time, no timeouts, max 0.5 s. Latency did not change through the 200–225 min window.
- **Final stream at 304.8 min:** one MF MJPG 720p30 stream start was normal: all steps S_OK, first frame at 598 ms, 90/90 frames, 29.6 fps, reader released in 902 ms.
- **Afterwards:** problem code 0, no re-arrival.

**Hypotheses** (all *inferred*; updated after run 3):
1. ~~**An age-dependent state at about 200–225 min after plug-in, exposed or tripped by the next stream start.**~~ **Not supported by run 3.** With no streaming, the camera answered every poll and started a stream cleanly at 304.8 min. Age alone does not trip the fault, and age does not leave a latent state that the next stream start exposes. (One sample.)
2. **Cumulative use or streaming.** R2 had about 270 Kiyo stream starts and about 380 control polls before the onset. R1 had the quick self-test streaming at 171–200 min, then nothing for 23.7 min. Both failures followed streaming, and run 3 (no streaming) did not fail, so this is now the leading hypothesis, possibly combined with age.
   - **Idle variant, still open:** run 3 polled every 10 s, so the Kiyo never sat idle, and R1's onset followed 23.7 idle minutes. A trigger of the form "idle → suspend/LPM → next stream start" is not excluded (see hypothesis 3).
   - *2026-11-11:* weakened by the 11-10/11 data. The Kiyo wedged on the first stream start about 4–5 min after a replug (17:04 on 11-10), and later ran more than 1,200 stream starts at 352–525 min before wedging in a DirectShow all-at-once round of W-MULTI at 525.2 min. Hypothesis 1 (age) is ruled out by the same data. See [windows_results_20261110.md](windows_results_20261110.md) §9.
3. **USB 3 LPM.** It is active on Gerald: LPM Moderate on AC and DC, selective suspend on (*measured*, [R2 W-ENV] `power`). Linux 7.0 carries a `NO_LPM` quirk for this exact device and symptom (plan §2.6, doc). Not tested; that is attended item A4.
4. **Vendor software.** LogiTuneAgent and RazerAppEngine held the Kiyo, without streaming, for the whole 84 min, and no vendor process started or stopped near the onset (*measured*, `vendor_process_changes`).
   - 75/75 MF cycles succeeded with Razer attached, so attachment alone does not break the camera (*measured*).
   - Their control traffic is not observed. The activity sampler is aliased by the camera lock: it never saw W-MULTI's own ffmpeg holds of the Kiyo.

**What to test next:**
1. **Fix the harness first** (§11): poll timestamps taken after the lock, a FIFO lock, problem code per poll, and W-MULTI child timeouts and mid-test fault gating. The next onset can then be timed to a second and attributed to a command.
2. **A4: LPM off** (power plan) after a fresh replug. Run a Kiyo-only loop, one stream start/stop per minute plus a control poll every 10 s, until failure or 6 h.
3. ~~**Control run.**~~ Done (run 3 above): no failure in 5 h of polls only, and the final stream was normal. Next is the S arm (a 10 s stream every minute plus polls, up to 6 h), then an idle arm (replug, untouched for about 3.5 h, then one stream start).
4. **Vendor-agent-off run.** Exit RazerAppEngine and LogiTune before the replug.
5. **USB 2.0 port arm** (A4).
6. **Rate the Kiyo's MJPEG modes, including its 60 fps modes, within 2 h of a replug.** W-MJPEG runs last in the suite (about 218 min in R2), so run it on the Kiyo alone or move it earlier.

## 9. Ratings per goal and API (final)

From R2 unless marked R1. Cell counts are per camera (C922 / Kiyo / generic / C930e). Sources: [R2 summary] and the per-test JSONs named in each row.

| Goal (test) | MF | DS via PyAV | DS via ffmpeg CLI | OpenCV `CAP_DSHOW` | Other |
| --- | --- | --- | --- | --- | --- |
| G-ID ([R2 W-ID]) | one cell for all 6 APIs: **partial (provisional)**, 1:1 and stable; reboot and replug not measured (A1) | ← | ← | ← | key source stability: yes |
| Reliability ([R2 W-CYC]) | **yes** ×12 (all 4 cameras, 3 variants) | yes ×9; **partial (format)** ×3 (Kiyo YUY2) | not cycled | **no (latency)** ×8 | – |
| G-MJPEG, in scope ([R2 W-MJPEG]) | yes / untested (fault) / yes / yes | yes / untested / yes / yes | not needed (0 fallbacks) | no JPEG bytes (REPORT finding 3) | – |
| G-MJPEG, all modes (R1, re-rated: [R1 a-mjpeg]) | partial (2 torn @5 modes) / untested / yes / partial (rate drift) | partial (25/120) / untested / yes / partial (22/119) | MJPEG in every mode where PyAV fell back | – | – |
| G-CTRL ([R2 W-CTRL-EFFECT]) | yes / partial / partial / partial | same as MF (DirectShow filter) | – | – | lists: MF = DS on all 4 (yes) |
| G-TS, tier 0 ([R2 W-TS]) | sample time **no** ×4; frame-index fit untested ×4 (no ground truth) | pts **no** ×4 (synthesized); frame-index fit untested ×4 | – | – | – |
| G-TS, tier 1 ([R2 W-TS]) | PTS and STC: **partial** (C922) / untested (Kiyo, 1 kHz PTS) / n/a / n/a | n/a (no metadata consumer) | n/a | – | – |
| G-BW ([R2 W-MULTI], [R2 W-TOPO]) | **yes** | – | **partial** (EIO ambiguous) | – | PyAV: partial; mapper: yes; W-TOPO G-BW: untested (predicts only) |
| Format lists ([R2 W-FMT]) | MF = DS = descriptors on every MJPEG mode: yes | ← | – | – | – |
| Listing without grabbing ([R2 W-FMT-NOGRAB]) | yes / yes / yes / no (2 OS-hidden modes) | – | ffmpeg `-list_options`: no / no / yes / no (min/max rates only) | no (asserted) | DirectShow filter: same as MF; hub IOCTL: yes ×4 (by construction); WinRT: no (asserted) |
| Kiyo control polling ([R2 W-KIYO]) | **no**: 190 of 294 polls answered per API; stopped at 210.5 min | ← | – | – | – |

Notes on reading the table (*inferred* from the verified analyses):
- **Two "yes" cells say less than they appear to.** The G-MJPEG yes cells for the generic and the C930e test only that MF and DS agree on the rate: the generic delivers 17 of the 30 fps requested. The hub-IOCTL completeness is true by construction.
- **Some partial and no cells are harness policy.** The three Kiyo DS reliability partials and the C930e MF/DS FMT-NOGRAB "no" are policy or an OS gap, not the API failing at its job.

## 10. What this means for the approach choice on Windows

- **Primary: MF native** (plan §3 row 1). It meets or beats DirectShow on every measured axis:
  - the same open/close reliability (630/630 each over both runs);
  - the requested MJPEG every time (360/360);
  - first frame 260–290 ms sooner;
  - a certain bandwidth code (`0x800718CF`) and a deterministic loser;
  - no re-enumeration of the generic camera after a refusal;
  - the only route to tier-1 PTS/SCR (*measured*, §2, §7, §4).

  plan §3's condition for choosing DirectShow instead ("only if MF fails W-CYC where DirectShow passes") did not occur.
- **Fallback: DirectShow through the ffmpeg CLI with `-vcodec mjpeg`, not PyAV.**
  - PyAV gets YUY2 whenever a raw caps entry matches: the Kiyo at 720p30, and 95–96 of about 120 Logitech modes in R1 (*measured*).
  - With the ffmpeg CLI, a refusal must be classified from the FFmpeg log ("Could not run graph" vs "RenderStream"), not from timing (*measured*).
  - A DirectShow retry must wait for the generic camera's 10 s re-enumeration (*measured*).
- **OpenCV `CAP_DSHOW` (skellycam today): replace it.** It opens reliably, but the configured stream takes 2.7–11.5 s, and `BUFFERSIZE` is a no-op. It reaches MJPG only because FOURCC is set last in the apply step, and it gives no JPEG bytes (*measured*).
- **Format discovery:**
  - MF `GetNativeMediaType` without `Start`, for the list a user sees;
  - the hub IOCTL, for descriptors and the mode-alt cache;
  - never ffmpeg's `-list_options`, which hides 720p30 MJPEG on two cameras (*measured*).
- **Controls:** through `IAMCameraControl`/`IAMVideoProcAmp` queried from the MF source. Apply them after the first frame and verify on the image. Keep a per-camera capability table: the generic's gain and WB are unusable, and the C930e resets exposure and gain at start (*measured*).
- **Modes:**
  - request ≥ 30 fps and decimate on the host (C922 MJPEG ignores lower rates and tears at @5, R1);
  - treat "60 fps" as unverified on the C922 under auto exposure (*measured*);
  - report the delivered rate to the user, since the generic gives 17–26 fps at @30 (*measured*).
- **Timestamps: undecided.**
  - Tier 0 has only the frame-index fit, which cannot be scored without the rig.
  - Tier 1 helps the C922 and possibly the Kiyo, and needs per-camera clock validation.
  - Dom's tier-1 decision (plan §8) should wait for A5.
- **Fault handling is part of the design** (*measured*, Kiyo):
  - a first-frame watchdog;
  - per-call timeouts on control queries;
  - a "replug needed" state after `0x8007001F`;
  - no automatic device restart (plan §6.1).

## 11. Harness limits and open items

**Harness bugs that affect conclusions** (each verified; file:line in `suite/`):

| Sev. | File:line | Bug | Fix |
| --- | --- | --- | --- |
| medium | `windows/tests/w_cyc.py:141` (+ `native/wincam.cpp:2335-2352`, `common/cycstats.py:113-117`) | fps is judged only for OpenCV. MF/DS `fps_mismatch` is always None and counts as 0, which hides the generic's 17 fps | emit `fps_measured` in wincam cycle rows, copy it in `_newproc_row`, apply the 0.9× rule to all APIs, add `n_fps_judged` |
| medium | `windows/tests/w_cyc.py:236-239` | `opencv_skellycam` sets FPS=30, but skellycam's default is −1, which skips that set | pass `--skellycam-framerate -1`; optionally a second variant at 30 |
| medium | `windows/tests/w_cyc.py:226-231`; `w_ts.py:547` | DS cycles and the DS timestamp capture use only PyAV, so the Kiyo DS cells measure PyAV's YUY2 fallback | add a `--engine ffmpeg` variant, or retry automatically on `capture_error.stage == 'format'` |
| medium | `common/rating.py:207-222`; `windows/tests/w_mjpeg.py:322-323` | the tier-0 fps reference is the MF/DS mean, so the criterion cannot fail; the label hides "rate not honoured" | append "rate not honoured in N" to the label; flag a tier-0 reference more than 2% off nominal |
| medium | `common/rating.py:644-649` with `windows/tests/w_fmt_nograb.py:437` | MF/DS are charged for the C930e modes that no API exposes; the hub IOCTL is rated against its own cache | rate MF/DS against an OS-exposed reference and report `descriptor_only_modes` separately; treat the hub IOCTL as the reference method |
| medium | `windows/tests/w_fmt_nograb.py:229-253` | blocker exclusion drops 897–1414 ms of the 2.5 s idle hold (1898 ms on the Kiyo) | sample a full blocker-free hold first; report `hold_coverage_fraction` |
| medium | `windows/tests/w_multi.py:354-359` | a child helper's own timeout is dropped, so the Kiyo's 35 s hang became `device_not_ready` with no health check | `timed_out = cmd.timed_out or s.get('timed_out') or s.get('hung')`; run the health check on `timeout` |
| medium | `windows/tests/w_multi.py:471-483` + `windows/suitectx.py:268-273` | a fault raised mid-test is not gated: the Kiyo was launched 15 more times, and `measurements.device_faults` is {} | also check `ctx.camera_faulted(key)` in `faulted()` |
| medium | `windows/suitectx.py:493-499` | `_scan_camcmd` records a failure only when the JSON has `ok:false`; controls JSON has no `ok` key, so the control timeouts were never recorded | treat an error dict, or an rc not in {0, None}, as a failure; also record multi-launch child failures (`w_multi.py:664-694`) |
| high | `windows/tests/w_kiyo.py:178-185, 242-257`; `tools/camlock.py:50-54` | poll time, age and activity are taken before the lock wait (up to 455.9 s); missed slots are caught up back to back; the non-FIFO lock starves the poller | stamp from wincam `utc_started`; set `next_due = max(next_due + interval, now)`; use a ticket lock; record `problem_code` per poll |
| medium | `windows/tests/w_ts.py:270`; `common/tsanalysis.py:803` | "self-consistent" means "regular against an ideal clock", which mixes cadence jitter with the units defect | report a units mismatch as its own flagged defect; keep the cell untested until the rig; fix the best-of tie-break at `w_ts.py:436` |
| medium | `windows/tests/w_ctrl_effect.py:463-472, 505-516, 538-545` | fixed set schedule (slow Kiyo DS sets left segments empty); persistence is always captured through MF, even on the DS leg | chain each set to the previous one's completion; capture persistence through the leg's own path |
| low | `common/topology_model.py:60, 1659-1662`; `windows/tests/w_multi.py:795-806` | marginal limit 93.75 µs, although 93.97 µs streamed; the stay-here advice drops to 1080p@5; the stagger text uses the step, not the real gap | seed the Intel bracket {pass 94.0, fail 101.1} or learn it; score (format, fps ≥ wanted, size); pass the real start gap |
| low | `windows/tests/w_mjpeg.py:307, 334, 364` | gated modes count as captured (Kiyo "4/4") and as failed modes | count only rows that are not skipped and have frames > 0 |
| low | `windows/tests/w_id.py:270-271` | the natural same-port replug evidence is unused | derive it from `arrivals_since_previous_run` plus the previous `discovery.json`; keep the cell provisional until A1 |
| low | `windows/tests/w_multi.py:73` | the 25 s re-arrival wait costs 16–19.5 s when no reset follows | wait for the learned delay + 2 s; extend to 25 s only if the camera is seen absent |

**Status 2026-11-09:** every row above is fixed in the harness code, as its Fix column says, and checked by offline tests (`suite/windows/tests/test_harness_fixes_offline.py` and the per-test offline tests). None has run on a camera yet. Notes on specific rows:
- W-CYC fps: wincam 1.2 emits `fps_measured` in every cycle row, so MF cycle rows are judged. Rows from wincam 1.1, including this report's runs, count as not judged on re-analysis.
- DS route: the DS-via-PyAV row is fixed by a `ds_ffmpeg_inproc` W-CYC variant and a third W-TS route, `ds_ffmpeg`. Both need the ffmpeg CLI on PATH.
- W-TS units defect: the units-defect row keeps a cell untested, with the defect flagged, until the rig (A5). The Kiyo's 1 kHz PTS is one such cell.

The full lists, with all low and cosmetic items, are in R2 `analysis/{mjpeg_fmt_nograb,cyc,multi_topo,ts,ctrl_id_env_kiyo}.md`.

**Open items:**
- **Attended items not yet run:** A1 (identity persistence), A2 (move a camera to a suggested port), A3 (clean metadata A/B; plan §2.2's cost to other applications was not re-measured), A4 (Kiyo with LPM off, or on USB 2.0), A5 (rig ground truth for G-TS) and A6 (cycles while another app holds the camera).
- **Kiyo:** its G-MJPEG cells (including the 60 fps modes) are unrated in both runs. Its DS route via the ffmpeg CLI was never cycled.
- **60 fps:** no in-scope 60 fps stream was verified at 60 fps. The C922 at 720p60 delivered 30.5 in every run.
- **Fits side:** the "fits" side of G-BW on a shared hub was tested only in R1. Under the mode scope, every HS13 pair is over budget except the 960x720 marginal case.
- **Sample size:** 90 cycles per camera and API bound reliability only at 0.96 (Wilson lower). A ≥ 99% claim needs at least 381 failure-free cycles per camera.
- **Conditions:** lighting and time of day changed between the runs (13:20–14:45 vs 17:49–19:13 local). This confounds the generic's rate, the C930e's post-start gain and the C922's PTS alternation amplitude. A controlled-light or fixed-exposure pass would remove it.
- **Second machine:** the Windows 10 22H2 machine has not been run.

[R2 summary]: ../results/windows/Gerald/suite_20261106T224912Z/summary.md
[R2 run_suite]: ../results/windows/Gerald/suite_20261106T224912Z/run_suite.json
[R2 suite_log]: ../results/windows/Gerald/suite_20261106T224912Z/suite_log.txt
[R2 discovery]: ../results/windows/Gerald/suite_20261106T224912Z/discovery.json
[R2 descriptors]: ../results/windows/Gerald/suite_20261106T224912Z/descriptors/descriptors.json
[R2 mode_alt_cache]: ../results/windows/Gerald/suite_20261106T224912Z/mode_alt_cache.json
[R2 W-ENV]: ../results/windows/Gerald/suite_20261106T224912Z/W-ENV.json
[R2 W-TOPO]: ../results/windows/Gerald/suite_20261106T224912Z/W-TOPO.json
[R2 W-ID]: ../results/windows/Gerald/suite_20261106T224912Z/W-ID.json
[R2 W-FMT]: ../results/windows/Gerald/suite_20261106T224912Z/W-FMT.json
[R2 W-FMT-NOGRAB]: ../results/windows/Gerald/suite_20261106T224912Z/W-FMT-NOGRAB.json
[R2 W-CTRL-LIST]: ../results/windows/Gerald/suite_20261106T224912Z/W-CTRL-LIST.json
[R2 W-CYC]: ../results/windows/Gerald/suite_20261106T224912Z/W-CYC.json
[R2 W-CTRL-EFFECT]: ../results/windows/Gerald/suite_20261106T224912Z/W-CTRL-EFFECT.json
[R2 W-TS]: ../results/windows/Gerald/suite_20261106T224912Z/W-TS.json
[R2 W-MULTI]: ../results/windows/Gerald/suite_20261106T224912Z/W-MULTI.json
[R2 W-MJPEG]: ../results/windows/Gerald/suite_20261106T224912Z/W-MJPEG.json
[R2 W-KIYO]: ../results/windows/Gerald/suite_20261106T224912Z/W-KIYO.json
[R2 a-ts]: ../results/windows/Gerald/suite_20261106T224912Z/analysis/ts.md
[R1 W-MJPEG]: ../results/windows/Gerald/suite_20261106T181941Z/W-MJPEG.json
[R1 W-CYC]: ../results/windows/Gerald/suite_20261106T181941Z/W-CYC.json
[R1 W-CTRL-LIST]: ../results/windows/Gerald/suite_20261106T181941Z/W-CTRL-LIST.json
[R1 discovery]: ../results/windows/Gerald/suite_20261106T181941Z/discovery.json
[R1 a-mjpeg]: ../results/windows/Gerald/suite_20261106T181941Z/analysis/mjpeg_fmt.md
[R1 a-cyc]: ../results/windows/Gerald/suite_20261106T181941Z/analysis/cyc_kiyo.md
[R1 a-multi]: ../results/windows/Gerald/suite_20261106T181941Z/analysis/multi_topo.md
