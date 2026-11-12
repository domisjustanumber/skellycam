# Exposure and gain for motion capture: how the exposure step should choose

Written 2026-11-11 for plan package 1.3 and TP1 (`research/CAPTURE_AND_RECORDING_PLAN.md` §1, §3.2, §3.3).
**Update 2026-11-12 (Dom, plan rev 3.4, D14):** the exposure step now looks for the **shortest exposure** whose matched-brightness image keeps D ≥ 0.80 × and ρ ≤ 1.5 × the reference, plus corner jitter when the board is in view (§5.2b). It replaces the §5.2a gain limit, and it caches what it learns per device for fast warm starts. Evidence: [windows_results_20261112.md](windows_results_20261112.md) §4.5–4.6.

**Update, later on 2026-11-11 (Dom's decisions, plan rev 3.3 D9–D12):** no per-model gain caps. The gain limit is measured on the live image in the exposure step (new §5.2a). White balance, zoom, pan, tilt and the image controls are locked at the camera's start values; power-line frequency follows local mains; AE priority is 0. The provisional caps below (128 / 230) are kept only as the evidence that motivated the rule.
Desk research plus re-analysis of saved result files. **No camera was opened and no setting was changed.**

Labels:
- **[M]** measured, in a result file we already have (linked);
- **[M, re-analysis]** computed in this study from frames the 11-11 suite run saved;
- **[C]** code (path:line, relative to the repo root);
- **[S]** primary source (URL, accessed 2026-11-11);
- **[W]** forum, press or user report;
- **[I]** inferred;
- **[arith]** arithmetic shown.

Main data: suite run `suite_20261111T040003Z` on Gerald, MJPEG 1280×720 at 30 fps, evening room light, a static desk scene ([summary](../results/windows/Gerald/suite_20261111T040003Z/summary.md)).
Method for the noise and size numbers: Appendix A.

---

## Recommendation

- **Pin gain at its minimum by default, but do not freeze it there.** On the C922, C930e and Kiyo the default gain *is* the minimum (0 of 0–255), which is also the lowest-noise value [M]. So "pin gain to default" is the right *starting* point. But in the room light of the 11-11 run, gain 0 needs about 31–40 ms (the −5 step) for mid-grey on the C922 and C930e [M]. That is 19–48 px of blur for a hand or limb at 2–5 m/s at 720p [arith]. Pinning gain at 0 there trades a small noise saving for a lot of blur (or for dark frames).
- **Order: exposure first, up to a blur ceiling; then gain, up to a limit measured on the live image (§5.2a); then warn the user to add light.** The step chooses the longest exposure that is ≤ the ceiling and does not overshoot the target brightness. Then it raises gain only as far as it needs to reach the target. Gain stays an output of the exposure step, never a user control. This is the same rule as industrial cameras' "minimize gain" auto profile with an exposure upper limit [S], but run **once before the session, with AE off**.
- **The ceiling is the smaller of a blur limit and a frame-period limit.** Blur limit: exposure ≤ blur budget ÷ image speed (table in §3). For example, about 2 ms (−9) for 2 px of blur at 2–3 m/s at 720p [arith]. Frame-period limit: an exposure longer than the frame period lowers the frame rate *even in manual mode with AE priority 0*. Manual −4 (62.5 ms) cut the C922 and C930e to 16.0 fps and the Kiyo to 19.4 fps [M, re-analysis]. So 30 fps allows at most −5 and 60 fps at most −6.
- **What gain costs, measured at equal brightness.** 3 stops shorter exposure plus high gain gave 1.3–2× the temporal noise. In absolute terms that is ≈0.5–0.7 → 0.8–1.1 grey levels after the camera's JPEG [M, re-analysis]. JPEG bytes per frame grew by 0–5 % (C930e up to +13 % in one run). Brightness drives JPEG size much more than gain does (C922: ×2 from luma 43 to 150). The Kiyo is the exception above gain 128: noise in mid-tones rose ~3× at gain 230. So cap it lower.
- **Per-camera rules.** C930e: resets exposure **and** gain at stream start, so apply them after the first frame and verify [M]. Generic 4c4a: gain does nothing visible and resets to 4 at every start [M]; the measured rule (§5.2a) stops at once because luma doesn't rise. Its exposure numbers are not 2^v s, so its blur ceiling cannot be enforced until its real exposure times are measured [M, re-analysis].

---

## 1. Per-camera gain: range, default, effect (question 1)

### 1.1 What the cameras report and do

| Camera | Gain range (step) | **Default** | As found 11-11 | Gain changes the image? | Holds through stream start? | Exposure range (default) |
| --- | --- | --- | --- | --- | --- | --- |
| Kiyo Pro 1532:0e05 | 0–255 (1) | **0** (= min) | 0 | Weakly: luma 119 → 134 → 151 at gain 26/128/230, exposure −7 (×1.27) | yes, 3/3 runs both paths | −11…−2 (−6) |
| C922 046d:085c | 0–255 (1) | **0** (= min) | 0 | Yes: luma 64 → 119 → 149 (×2.3) | yes, 3/3 | −11…−2 (−5) |
| C930e 046d:0843 | 0–255 (1) | **0** (= min) | **5** (while AE on) | Yes: luma ~43 (reset value) → 115 → 148 | **no**: read 2–4 at the first in-stream set in 5/6 runs (25 once) | −11…−2 (−5) |
| generic 4c4a:4a55 | **1–7** (1) | **4** (mid-range) | 4 | **No**: luma 165.6 / 165.6 / 165.5 at gain 2/4/6 (×1.00) | **no**: reads 4 at the first frame in 3/3 runs | −7…3 (−7) |

Sources: ranges, defaults and as-found values [M] from [W-CTRL-LIST](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST/), files `*_controls_{mf,ds}.json`, `controls[key=pa.gain|cc.exposure]`. MF and DS agree on every camera. Effects and holding [M] come from [W-CTRL-EFFECT.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json), `paths.{mf,ds}.controls.gain.runs[*].metric_values` and `sets[*].before_value`, matching [windows_results_20261110.md](windows_results_20261110.md) §"Effect in the image".

The known facts check out:
- **C930e resets exposure and gain at stream start.** Exposure was reset to −5 in 3/3 runs on both paths, and gain was not held in 5/6 runs [M].
- **The generic camera's gain has no visible effect** [M].
- **The C922's gain range is 0–255** [M]. So are the Kiyo's and the C930e's.

Gain on all four cameras has only a `manual` capability flag (`caps_flags_names: ["manual"]`). There is no auto flag on gain [M] ([W-CTRL-LIST](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST/)). This matches the UVC model: gain has no auto mode of its own, and automatic gain is part of the camera's auto-exposure (§2.4).

### 1.2 What gain costs at equal brightness (the comparison that matters)

The useful question is not "is gain 230 noisier than gain 0 at the same exposure". It is, because the picture is also brighter. The useful question is **"at the same output brightness, how much worse is short exposure + gain than long exposure + no gain?"**

The 11-11 frames contain such pairs, because exposure was swept at low gain and gain was swept at exposure −7. *Noise* is the temporal noise in flat image areas: frame-to-frame standard deviation in 8-bit luma, after the camera's processing and JPEG (Appendix A). *Detail* is the mean absolute horizontal gradient. AF and AWB were on during these runs, so detail and bytes can shift with focus. Flat-area noise is robust to that.

| Camera | Long exposure, low gain | Short exposure + gain (3 stops shorter) | Noise ratio | JPEG bytes | Detail |
| --- | --- | --- | --- | --- | --- |
| C922 | −4 (62.5 ms), gain 0: luma 153, noise 0.66 (mid-tone bin 100–140: 0.69), 234 kB, detail 4.88 | −7 (7.8 ms), gain 230: luma 149, noise 0.89 (bin 100–140: 1.12), 240 kB, detail 4.32 | ×1.35 overall, ×1.6 in mid-tones and shadows | +3 % | −11 % |
| C930e | −5 (31 ms), gain ≈3–5 (after reset): luma 114, noise 0.54, 116 kB | −7, gain 128: luma 115, noise 0.80, 119 kB | ×1.5 | +3 % | same |
| C930e | −4, gain ≈5: luma 162, noise 0.45, 118 kB | −7, gain 230: luma 148, noise 0.86, 124 kB (119–135) | ×1.9 | +5 % (up to +13 %) | −7 % |
| Kiyo | −4, gain 0: luma 126, noise 0.63, 208 kB | −7, gain 128: luma 134, noise 0.80, 219 kB | ×1.27 | +5 % | −11 % (focus confounded) |
| Kiyo | −7, gain 0: luma 111, noise 0.65 | −7, gain 230: luma 151, noise 1.06; **bin 140–180: 2.07 vs 0.67** | ×1.6 overall, **×3 in bright mid-tones** | n/a | much lower (2.73 vs 4.44; focus confounded) |
| generic | gain 2 / 4 / 6 at fixed exposure −2: luma 165 for all | — | noise 1.26 / 1.13 / 1.47: not monotonic, small | 105 kB for all (DS) | — |

All rows [M, re-analysis] from the W-CTRL-EFFECT frames (6 segments per cell: 3 runs × MF and DS). The Kiyo's DS path delivered raw YUY2, so Kiyo bytes are MF only, and its YUY2 noise numbers agree with the JPEG ones within ~10 %.

Caveats:
- The long-exposure partners at −4 ran at 16–19 fps (§3.3), so they are a reference for noise, not a usable mocap setting.
- Brightness is matched only within 3–10 %.
- One static scene in evening room light.

### 1.3 Verdict per camera

| Camera | Lowest-noise gain | Is "default" a sensible pin? | Notes |
| --- | --- | --- | --- |
| Kiyo | 0 | **Yes: default = minimum.** Raise only if needed; provisional cap **128** | Above 128, noise in bright mid-tones roughly triples and detail drops [M, re-analysis]. Its luma responds weakly to both exposure and gain (−9 → −7 → −4: luma 70 → 111 → 126) [M]. It was also found with non-default brightness 159, contrast 201 and backlight compensation 1 [M] ([W-CTRL-LIST](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST/usb_video_device_1532-0e05_controls_ds.json)). Those controls change the luma mapping, so they may explain the compressed response [I] |
| C922 | 0 | **Yes: default = minimum.** Raise as needed; provisional cap **230** (the highest value measured) | Gain 230 brightens about as much as 3 stops of exposure (g230 at −7 → 149; g0 at −4 → 153) [M] |
| C930e | 0 | **Yes: default = minimum**, but it must be **re-applied after stream start**, because the camera puts back ~2–5 | Gain 128 ≈ +2 stops (−7 g128 = 115 ≈ −5 g≈4 = 114) [M]. Provisional cap **230** |
| generic | unknown (gain 1 was never tested; 2/4/6 look the same) | Default 4 is **mid-range**, but gain has no visible effect and is reset to 4 at stream start [M] | Leave it at 4 and do not use it as an adjustment. This is effectively "pin to default" |

So the owner's expectation ("probably means just pinning gain to default") is **right about which value is lowest-noise** on three of four cameras. It is **wrong as a fixed rule**: in normal indoor light it forces either long exposures (blur) or dark frames. The evidence shows that moderate gain costs much less image quality than that blur does (§2, §3, §4).

---

## 2. What gain does: physics and practice (question 2)

### 2.1 Where the noise comes from
- **Shot noise is fixed by physics.** The number of photo-electrons in a pixel is Poisson-distributed, so its variance equals its mean, σₑ² = μₑ. All other noise (readout, amplifiers) can be modelled as one signal-independent term σ_d², plus ADC quantization σ_q² = 1/12 DN² [S] ([EMVA 1288 Release 4.0 Linear](https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf), §2.4 Eq. 13–15).
- **SNR depends on photons collected, not on gain.** EMVA 1288 gives SNR(μ_p) = ημ_p / √(σ_d² + σ_q²/K² + ημ_p). "Except for the small effect caused by the quantization noise, the overall system gain K cancels out" [S] (same document, §2.6 Eq. 21–22).
  - In bright light SNR ≈ √(ημ_p), i.e. shot-noise-limited.
  - In dim light SNR ≈ ημ_p / σ_d, i.e. read-noise-limited.
- **So the real trade is exposure time, not gain.** Cutting exposure by 3 stops means 8× fewer photons. In the shot-noise-limited regime that lowers SNR by √8 ≈ 2.8× [arith]. Gain only restores the brightness. It cannot restore the lost photons.
- **Our cameras show less than 2.8×.** The measured noise increase at equal brightness was 1.3–2× (§1.2). The cameras' noise reduction and JPEG quantization remove part of the noise, and partly turn it into lost detail instead: −7 to −11 % gradient energy on the C922 and C930e [M, re-analysis]; the interpretation is [I].
- **The noise levels themselves are small.** About 0.5–1.1 grey levels (8-bit) on the three branded cameras, against 1.1–2.9 on the generic at any setting [M, re-analysis]. These are post-ISP, post-JPEG values, not EMVA-conformant sensor measurements [I].

### 2.2 Analog vs digital gain
- **Definitions.** "Analog gain is applied before the signal from the camera sensor is converted into digital values." "Digital gain is applied after the conversion, i.e., it is basically a multiplication of the digitized values." [S] ([Basler docs: Gain](https://docs.baslerweb.com/gain)).
- **Analog gain helps only in dim light.** It amplifies the signal before the ADC and the later electronics, so their noise and the quantization step become smaller relative to the signal. That is the σ_q²/K² term in the EMVA formula, so it helps a little in the read-noise-limited regime [S, EMVA Eq. 21] [I for the interpretation].
- **Digital gain adds nothing.** It multiplies signal and noise equally, adds no information, and throws away levels and highlight headroom [I, follows from the definition].
- **Example sensor: Sony IMX327**, which press reports name as the Kiyo Pro's sensor [W] ([Tom's Hardware review](https://www.tomshardware.com/reviews/razer-kiyo-pro-webcam-review-a-new-hardcore-standard)). Its PGA gives "0 dB to 29.4 dB: Analog Gain … 29.7 dB to 71.4 dB: Analog Gain 29.4 dB + Digital Gain 0.3 to 42 dB (step pitch 0.3 dB)" [S] ([Sony IMX327LQR/LQR1 Product Information v1.3, mirror](https://www.1stvision.com/cameras/sensor_specs/IMX327.pdf)). So the top part of a webcam's gain range is likely digital [I].
- **The UVC number is not in dB.** How a UVC gain value (0–255) maps to sensor dB, and where analog ends, is vendor-defined and not published for any of our cameras. Microsoft: "The range for gain is vendor-defined" [S] ([KSPROPERTY_VIDEOPROCAMP_GAIN](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-videoprocamp-gain)). A libcamera patch notes that UVC gain has no units and that cameras expose very different ranges [W] ([libcamera-devel 2020-04](https://lists.libcamera.org/pipermail/libcamera-devel/2020-April/008169.html)).

### 2.3 What this means for the exposure step
- **Bright room:** no gain is needed. The exposure step lands below the ceiling with gain at its minimum.
- **Dim room, motion matters:** a short exposure plus gain gives a slightly noisier but sharp image. A long exposure with no gain gives a cleaner but smeared image. For tracking, blur is the bigger problem (§4).
- **Too dark at gain 0, and gain not allowed:** the image stays dark. In an 8-bit JPEG pipeline, a dark image keeps only a few grey levels in the shadows, and JPEG quantizes those coarsely. Analog gain applied *before* the ADC and JPEG keeps more of the signal than brightening the recorded frame afterwards [I].

### 2.4 How webcam auto-exposure trades gain against exposure time
- **UVC has no separate auto-gain switch.** The UVC auto-exposure mode control has four modes: manual, auto, shutter priority and aperture priority. They are described in terms of exposure time and iris only. Gain is a plain value with no auto mode [S] ([libuvc `standard-units.yaml`](https://raw.githubusercontent.com/libuvc/libuvc/master/standard-units.yaml), which transcribes the UVC control definitions; the UVC PDF itself was not read). Our cameras list gain as manual-only [M]. *Inferred:* "auto gain off" in practice means "AE mode = manual". Whatever gain the camera's AE used is then frozen, or reset (C930e), until we set it.
- **The cameras' AE does change gain internally.**
  - C930e: under AE its gain readback was 5, not the default 0 [M] ([W-CTRL-LIST](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST/logitech_webcam_c930e_046d-0843_controls_ds.json)).
  - C922: under AE in the same light, exposure read −7 with luma 119–125 [M] ([W-AUTO.json](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO.json), `baseline.auto_values_read`, `baseline.luma`). Manual −7 at gain 0 gives luma 43 [M]. *Inferred:* the C922's AE adds about +1.5 stops of gain (or ISP brightening) that the gain control does not report.
- **Typical AE policy: exposure first, gain only after an exposure limit.** Basler documents this explicitly: "Minimize Gain: the gain is kept as low as possible" and gain rises only once exposure reaches its upper limit. "Smart" keeps gain low and the frame rate high, raising exposure until the frame rate would drop, then gain up to a limit [S] ([Basler docs: Auto Function Profile](https://docs.baslerweb.com/auto-function-profile)).
- **Consumer webcam AE favours low noise over low blur.** With AE priority on (C930e: 1), it also lets the frame rate drop [S] ([KSPROPERTY_CAMERACONTROL_AUTO_EXPOSURE_PRIORITY](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-auto-exposure-priority)). In the 11-11 light, the C930e's AE settled at −5 (31 ms) [M] (W-AUTO `auto_values_read`). That is the "pin gain low, accept blur" policy, which is wrong for mocap [I].

### 2.5 Gain and JPEG size (bytes per frame, USB, disk)
- **Gain adds little JPEG size; brightness adds a lot.** At equal brightness, the gain-heavy frames were 0–5 % larger (C930e up to +13 % in one run) [M, re-analysis, §1.2]. The bigger effect is brightness itself. On the C922, 112 kB at luma 43 rose to 169 kB at luma 64, 204 kB at 119 and 240 kB at 149, whether the brightness came from gain or from exposure [M, re-analysis].
- **In-camera noise reduction can offset noise growth.** The Kiyo's frames got *smaller* from gain 128 to 230 (219 → 204 kB) while detail dropped [M, re-analysis].
- **Bandwidth.** At 240 kB × 30 fps ≈ 7.2 MB/s per 720p camera [arith], within what USB 2.0 carries. On USB 2.0 isochronous, the bandwidth reservation is fixed by the alternate setting chosen at stream start, not by each frame's size [I]. Frame size matters for disk and recording throughput: the recorder writes the camera's JPEG bytes unchanged (plan §2.1).
- **Conclusion:** noise-driven size growth is not a reason to avoid moderate gain.

---

## 3. Motion blur budget (question 3)

### 3.1 Geometry and formula
- **Blur length** (px) = image speed (px/s) × exposure time (s).
- **Image speed** = subject speed v (m/s) × px per metre at the subject.
- **px per metre** = image width W ÷ (2 · d · tan(HFOV/2)).
- **Assumed:** HFOV 70° (C922-class), subject distance d = 3 m. The image then covers 4.20 m, which gives 304.7 px/m at 1280 wide and 457.0 px/m at 1920 wide [arith].
- **Exposure ceiling:** E_max = B / (v · px_per_m), for a blur budget of B px.
- **Subject speeds** below are assumptions, not measurements: about 1 m/s for the torso and slow limbs, 2–3 m/s for hands and feet in everyday motion, 5 m/s for fast limbs, 10 m/s for kicks and punches [I].

### 3.2 Exposure ceilings (largest Windows step 2^v s that fits)

| Speed | 720p, B = 1 px | 720p, B = 2 px | 720p, B = 5 px | 1080p, B = 1 px | 1080p, B = 2 px | 1080p, B = 5 px |
| --- | --- | --- | --- | --- | --- | --- |
| 1 m/s | 3.28 ms → −9 | 6.56 ms → −8 | 16.4 ms → −6 | 2.19 ms → −9 | 4.38 ms → −8 | 10.9 ms → −7 |
| 2 m/s | 1.64 → −10 | 3.28 → −9 | 8.21 → −7 | 1.09 → −10 | 2.19 → −9 | 5.47 → −8 |
| 3 m/s | 1.09 → −10 | 2.19 → −9 | 5.47 → −8 | 0.73 → −11 | 1.46 → −10 | 3.65 → −9 |
| 5 m/s | 0.66 → −11 | 1.31 → −10 | 3.28 → −9 | 0.44 → −12 | 0.88 → −11 | 2.19 → −9 |
| 10 m/s | 0.33 → −12 | 0.66 → −11 | 1.64 → −10 | 0.22 → −13 | 0.44 → −12 | 1.09 → −10 |

All [arith]. −12 and −13 are below every tested camera's minimum (−11; the generic's is −7) [M]. Frame rate does not enter the blur ceiling; it sets a separate ceiling (§3.3).

The other direction, blur per setting at 3 m [arith]:

| Setting (nominal) | 720p, 2 m/s | 720p, 5 m/s | 1080p, 2 m/s | 1080p, 5 m/s |
| --- | --- | --- | --- | --- |
| −10 (0.98 ms) | 0.6 px | 1.5 px | 0.9 px | 2.2 px |
| −9 (1.95 ms) | 1.2 | 3.0 | 1.8 | 4.5 |
| −8 (3.9 ms) | 2.4 | 6.0 | 3.6 | 8.9 |
| −7 (7.8 ms), skellycam default [C] `skellycam/core/camera/config/camera_config.py:25` | 4.8 | 11.9 | 7.1 | 17.9 |
| −6 (15.6 ms), upstream's longest RECOMMEND result | 9.5 | 23.8 | 14.3 | 35.7 |
| −5 (31.3 ms), upstream manual cap | 19.0 | 47.6 | 28.6 | 71.4 |

### 3.3 Frame-rate side effect of long exposures
- **Manual long exposures lower the frame rate even with AE priority off** [M, re-analysis] (W-CTRL-EFFECT MF exposure runs, delivered rate from MF sample times; 3 runs each):
  - C922: −9 and −7 ran at 30.2 fps; **−4 (62.5 ms) ran at 16.0 fps**, with `auto_exposure_priority` = 0.
  - C930e: 30.1 fps at −9 and −7; **16.0 fps at −4** (priority 1).
  - Kiyo: 30.1–30.4 fps at −9 and −7; **19.4 fps at −4** (priority 0). *Inferred:* the Kiyo's −4 is about 50 ms, not 62.5.
  - generic: 25.5–26.5 fps at −5, −2 and 1 alike. Its 25.7 fps is therefore not caused by AE, contrary to the inference in [windows_results_20261110.md](windows_results_20261110.md). Its exposure numbers cannot be 2^v s, because "−2" (250 ms) and "1" (2 s) still ran at 25.7 fps.
- **Microsoft's documentation agrees.** "if the frame rate is 30 fps, the exposure time cannot exceed 33 ms" without AE priority. AE priority is only valid in auto-exposure mode [S] ([KSPROPERTY_CAMERACONTROL_AUTO_EXPOSURE_PRIORITY](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-auto-exposure-priority)).
  - So in **manual** mode AE priority does not protect the frame rate. TP1's note that turning AE priority off means "exposure cannot lower the frame rate [I]" is contradicted by the C922 measurement above.
  - **skellycam itself must cap exposure below the frame period.**
- **Frame-period ceiling** = largest 2^v ≤ 1/fps:
  - 30 fps (33.3 ms) → **−5** (31.25 ms, 94 % of the period); 60 fps (16.7 ms) → **−6** (15.6 ms, 94 %) [arith].
  - −5 at 30 fps is measured only on the C930e (its stream-start reset to −5 ran at 30.1 fps) [M, re-analysis].
  - −6 at 60 fps is untested. Only the C922 has a 60 fps mode in scope [M] ([windows_results_20261110.md](windows_results_20261110.md)).
- **Upstream cap.** `MAX_MANUAL_EXPOSURE = -5` [C] (`upstream/sfn26:skellycam/core/camera/config/camera_config.py:26`).
  - It is a 30 fps frame-period guard, not a blur guard ([skellycam_exposure_review.md](skellycam_exposure_review.md) §4).
  - At 60 fps it would allow an exposure longer than the frame [I].
  - At 720p it still allows 19–48 px of blur at 2–5 m/s [arith].
- **This checkout has no cap.** Its UI allows −13…−4 [C] (`skellycam-ui/src/components/camera-config-panel/CameraConfigExposure.tsx:13`). RECOMMEND searches −12…−4 and returns the step nearest whole-frame mean 127.5, minus one [C] (`skellycam/core/camera/opencv/opencv_helpers/recommend_camera_exposure_setting.py:9-12, 49, 99`).
- **skellycam never sets gain** [C]: there is no `CAP_PROP_GAIN` or gain field anywhere in `skellycam/` (grep).

### 3.4 Other timing effects worth knowing
- **Windows exposure steps are coarse.** The Windows camera API expresses exposure as log2 seconds: −7 = 1/128 s, −6 = 1/64 s [S] ([KSPROPERTY_CAMERACONTROL_EXPOSURE](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-exposure)). UVC's own absolute exposure control uses 100 µs units [S] ([libuvc](https://raw.githubusercontent.com/libuvc/libuvc/master/standard-units.yaml), `exposure_abs`). So on Windows the step can only move exposure in factors of 2 [I]. **Gain is the only fine brightness adjustment between those steps**, which is a second reason to let the step use a little gain.
- **Flicker under mains lighting.** Mains-powered lights flicker at 100 or 120 Hz (8.3–10 ms period). An exposure shorter than one flicker period shows brightness that varies frame to frame, and as bands under a rolling shutter [I]. The 11-11 frames showed no row banding at −7 (noise with row means removed within 4 % of total noise) [M, re-analysis], but the room light is unknown. The UVC power-line-frequency control only helps the camera's own AE [I]. Short exposures for fast motion therefore also need flicker-free light. TP1 should measure it (§6, T1).
- **Rolling-shutter skew is separate from blur.** Readout takes up to ~30 ms per frame on the C922 (upper bound) ([rolling_shutter/README.md](../../rolling_shutter/README.md)). At 2 m/s at 720p (610 px/s) that is ~18 px of top-to-bottom skew [arith]. It is the same at every exposure [I]. Short exposures remove blur, not skew.

### 3.5 How much light the ceiling needs (example from the 11-11 room)
- **C922 at gain 0:** −9 → luma 10, −7 → 43, −4 → 153 [M]. Mid-grey (~120) needs about −4.6 (~40 ms), interpolating in log exposure [arith]. That is already beyond the 30 fps ceiling.
- **To get −9 (2 ms, the 2 m/s / 2 px ceiling at 720p):**
  - at gain 0, about 4.6 stops (~25×) more light;
  - with gain 230 (≈ +3 stops), about 1.6 stops (~3×) more [arith, from M, treating luma as roughly linear in exposure near mid-grey (I)].
- **C930e:** similar (−5 at gain ≈4 → 114) [M].
- **Kiyo:** more sensitive (−7 at gain 0 → 111) [M]. Consistent with a low-light STARVIS sensor [W].
- **In short:** short mocap exposures need much brighter light than a living room, plus some gain. The step must say so instead of quietly lengthening the exposure.

---

## 4. Does noise matter for keypoint trackers and ChArUco? (question 4)

- **Pose estimators: blur hurts more than noise, at benchmark levels.** Wang et al., CVPR 2021, applied ImageNet-C corruptions at 5 severities to COCO and other datasets [S] ([arXiv 2105.06152](https://arxiv.org/pdf/2105.06152), Table 1).
  - HRNet-W32 at 256×192 had AP 74.4 clean. Averaged over the five severities it scored 51.3 under Gaussian noise, 54.2 under shot noise and **43.5 under motion blur**.
  - The authors: all models "are more robust to weather or brightness changes, while less robust to motion or zoom blur."
- **The paper's noise is far stronger than ours.** The mildest Gaussian severity has σ = 0.08 of full scale, i.e. ≈20 grey levels [S] ([ImageNet-C `corruptions.py`](https://raw.githubusercontent.com/hendrycks/robustness/master/ImageNet-C/imagenet_c/imagenet_c/corruptions.py): `c = [.08, .12, 0.18, 0.26, 0.38]`). Our worst branded-camera temporal noise at gain 230 was ≈1–2 grey levels [M, re-analysis].
- **The paper's blur is about the size our long exposures produce.** Motion-blur radii run 10–20 px on ~640 px-wide COCO images [S, same file]. That is in the range −6 and −5 produce for 2–5 m/s at 720p (§3.2) [I].
- **What this supports:** at the gain levels in question, blur is the likelier cause of keypoint error [I].
- **ChArUco / OpenCV markers fail on blur and on darkness.**
  - "OpenCV methods start to completely fail (0% detection accuracy) for kernel sizes of 6 and larger" for horizontal motion blur [S] ([Deep ChArUco, Hu et al., CVPR 2019](https://ar5iv.labs.arxiv.org/html/1812.03247), §5.1.1).
  - Under synthetic darkening "the OpenCV detector fails at the rescaling factor of 0.6^4" (≈13 % brightness) [S] (same, §5.1.2).
  - Implication: calibration recordings need blur under ~5 px and must not be left dark. Gain is better than darkness there [I].
- **A further, uncited concern:** square-marker corner localization suffers from frame-to-frame pixel jitter, which is noise [W/S, secondary summary of a KIT paper; not read in full]. How much noise at our levels moves ChArUco corners is **unknown**.
- **MediaPipe Pose and RTMPose specifically:** no published measurement of sensitivity to sensor noise at webcam levels was found. **Unknown.** (The owner already declined a keypoint-vs-quality test for compression; none is proposed here.)

---

## 5. Proposed algorithm for the exposure step (question 5)

### 5.1 Inputs
- **Frame rate** (requested), plus delivered fps measured during the step.
- **Motion setting**, mapped to a blur ceiling. Presets [I], from §3.2 at B = 2 px, d = 3 m, HFOV 70°:
  - "Slow" (1 m/s): −8 at 720p and 1080p.
  - "Normal" (2 m/s, default): −9.
  - "Fast" (5 m/s): −10 at 720p, −11 at 1080p.
  - Advanced: blur px and speed. Show the result in ms.
- **Target brightness:** median luma of the central 80 % of the frame, ≈110, band 95–125, with at most 1 % of pixels ≥ 250 (highlight guard) [I].
  - This replaces today's whole-frame mean 127.5 minus one stop [C] (`recommend_camera_exposure_setting.py:12, 49, 99`).
  - The suite already uses the central-80 % luma ROI [C] (`research/usb_cameras/suite/windows/tests/w_ctrl_effect.py:271`).
- **Per-camera data:** ranges and defaults read live from the device. No per-model table: the gain limit is measured (§5.2a), and resets at stream start are detected by reading back after the first frame (§5.3). §5.4 records what each camera did, as test expectations.

### 5.2 Decisions, in order
1. **Lock auto modes.** Set AE mode = manual, AF off, AWB off, holding the white-balance value it had at start (read it, switch AWB off, set that value and read it back; D10), and AE priority = 0 where present (harmless; it only matters in AE mode [S]). Read the flags back.
   - **Lock the rest at their start values (D11, D12):** read white balance, zoom, pan, tilt, brightness, contrast, saturation, sharpness, gamma and backlight compensation as the camera starts, and keep those values; do not reset them to defaults. Set power-line frequency to local mains (from the OS region; 60 Hz on Gerald) and AE priority to 0 where present. Record every value. When a stored calibration is loaded and its recorded values differ from the camera's start values, list the controls that differ and ask the user what to do (apply the stored values, keep the current ones and recalibrate, or cancel). Never change them silently.
2. **Compute the ceiling** v_ceil = min(v_blur, v_fps, v_dev_max), where v_fps = ⌊log2(1/fps)⌋ (−5 at 30 fps, −6 at 60 fps).
   - If v_ceil < v_dev_min (the camera cannot go that short), use v_dev_min and warn "camera X cannot expose short enough for this motion setting".
3. **Gain = minimum** (= default on the Kiyo, C922 and C930e). Every camera, including the generic (its minimum is 1 and its start value 4; the rule below finds gain ineffective there).
4. **Exposure first.** From v_ceil downwards, take the **longest** step whose luma does not exceed the band top and does not clip more than 1 %.
   - The ceiling is the upper limit, never a target: in bright light a shorter step is chosen.
   - At most 4–7 steps; luma rises monotonically with exposure on the three branded cameras [M].
5. **Then gain, only if short of the target.** At that exposure, binary-search gain in [min, g_lim] for luma ≈ target, where g_lim is measured on the way (§5.2a).
   - Luma rose monotonically with gain in all 18 runs on the three branded cameras [M] (`monotonic: true`).
   - About 8 probes for 0–255.
   - This also fills the 2× gaps between exposure steps (§3.4).
6. **If still too dark at g_lim,** keep the ceiling: do not lengthen exposure past it. Then:
   - accept the darker image if luma ≥ ~60 [I];
   - warn: "Camera X is about N× too dark for <motion setting> at <fps>: add light, or choose a slower motion setting". N ≈ target ÷ achieved luma, a rough estimate [I];
   - only the user may choose to relax the motion setting.
7. **Optional common exposure:** use the same exposure on all cameras (the shortest chosen) and let gain differ, so every view has the same blur [I]. Cost: more gain on the brighter-exposed cameras.

### 5.2a Measuring the gain limit on the live image (D9)

> **Superseded on 2026-11-12 by §5.2b (plan D14).** The 11-11/12 hardware run showed two problems with this rule. ρ *falls* with gain on the C922 and C930e, so the "ρ rises" assumption is wrong. And comparing D at a fixed exposure penalises brightness as well as gain ([windows_results_20261112.md](windows_results_20261112.md) §4.5). This section is kept for the record. §5.2 steps 4–6 are replaced by §5.2b as well.

Dom, 2026-11-11: no list of gain caps per camera model; the gain noise is measured as part of the exposure step. Proposed method [I unless marked]:

- **What ideal gain does.** At a fixed exposure, analog gain scales signal and noise together, so for the same scene pixels the relative noise σ/μ stays about the same, or falls slightly where read noise after the gain stage matters (§2.1–2.2) [S, EMVA 1288]. If σ/μ for the same pixels **rises** as gain goes up, the extra comes from digital gain, quantization or the camera's processing. That's the cost to stop at.
- **The evidence fits.** Kiyo at −7, gain 0 → 230: overall σ/μ rose ×1.20 [arith: (1.06/151) ÷ (0.65/111)]. For the pixels that land in the 140–180 bin at gain 230, it rose about ×2.3 [arith: (2.07/160) ÷ (0.66/118), assuming those pixels sat near 118 at gain 0 with noise ≈ the overall 0.66]. That matches the "noise triples in bright mid-tones above 128" finding (§1.2). The per-pixel version is [NV]: the 11-11 analysis didn't track matched pixel sets.
- **Measurement per gain probe** (the same probes as step 5, at the chosen exposure):
  - discard ≥ 200 ms of frames, then decode **8 consecutive frames** to Y (the camera's JPEG, as everywhere in this doc);
  - **flat mask**, fixed for the whole step from the gain-minimum frames: pixels in the central 80 % ROI with low spatial gradient, luma 30–220 at gain minimum (away from clipping at higher gain);
  - per-pixel temporal σ over the 8 frames, and the per-pixel mean μ; take the **median of σ/μ** over the mask: the relative noise ρ(g). The median limits the effect of a few moving pixels;
  - **detail** D(g): mean gradient magnitude over the textured part of the ROI ÷ mean luma (ideal gain leaves this unchanged; noise reduction smearing lowers it);
  - **gain response**: μ(g) ÷ μ(g_min) over the mask.
- **Rule (thresholds provisional; T1 sets them):** g_lim is the highest probed gain where
  - ρ(g) ≤ 1.5 × ρ(g_min), and
  - D(g) ≥ 0.85 × D(g_min), and
  - luma still rises: the last probe raised μ by ≥ 3 %. If gain has no visible effect (the generic camera [M]), g_lim = g_min and gain is left alone.

  The binary search assumes ρ rises monotonically with gain [I]; T1 checks that.
- **Motion guard.** The step needs a mostly still scene (it already assumes that for luma). If more than 5 % of mask pixels change by more than 10 grey levels between consecutive frames, the probe is retried (up to 3 times). After that, g_lim falls back to the highest gain already verified (g_min if none), and the result is flagged `gain_limit_unverified` with a "hold still / clear the view" message.
- **Cost:** 8 frames + 200 ms ≈ 0.47 s per probe at 30 fps, 0.33 s at 60 fps; about 8 gain probes ≈ 4 s per camera, all cameras in parallel. The whole step goes from ≈ 4–5 s to ≈ 8–9 s [arith].
- **Record** g_lim, ρ(g_min), ρ(g_lim), the D ratio, the gain response and any flag with the other exposure-step outputs. Each run measures afresh; nothing is looked up by model.

### 5.2b Shortest exposure at matched brightness (D14, Dom 2026-11-12)

**Goal (Dom):** the shortest exposure time that adds the least noise and softness. This replaces §5.2 steps 4–6 and §5.2a. Steps 1–3 of §5.2 (lock auto modes, D10–D12 values, the frame-rate ceiling) are unchanged. D9 still holds: no per-model table; every decision is measured on the live image.

**Evidence** [M] ([windows_results_20261112.md](windows_results_20261112.md) §4.5, `W-GAIN.json`). At matched brightness, trading exposure for gain costs each camera something different:

| camera | what gain costs | at 2 ms with matched brightness |
|---|---|---|
| C930e | **noise** | ρ ×2.3, D flat |
| C922 | mostly **softness** (its processing smooths) | D ×0.56, ρ ≤ ×1.5 |

So the score needs both D and ρ, and it must be taken at matched brightness.

#### Method, per camera

All cameras run at once in one pymf process, on a running stream, after the first frame.

1. **Ceiling** v_max: the longest step that keeps delivered fps ≥ 0.99 × nominal, **measured**. Start at ⌊log2(1/fps)⌋ and step down until it passes (≈ 1.5 s of frames per check). On 11-11/12 [M]: Kiyo Pro −7, C922 and C930e −5 at 30 fps. If the user set a motion preset (§5.1), v_max = min(that ceiling, the motion ceiling): the motion preset is a hard limit.
2. **Free speed first:** at gain minimum, step down from v_max while the target ROI still reaches the target luma (§5.1 band). The shortest such step is the reference e0.
   - If v_max at gain minimum is already too dark, the camera is **light-limited**. Use the §5.2 step-6 warning (how many stops are missing) before any gain is used, and continue the search from v_max.
3. **Reference at e0, gain minimum:** luma L_ref, detail D_ref (§5.2a definition: mean Sobel gradient on the textured mask ÷ its luma, on the probe's frame mean) and noise ρ_ref (median per-pixel σ/μ on the flat mask). With the ChArUco board in view, also corner jitter (px RMS over 60 frames) and the corner count.
4. **Step down one exposure step at a time.** Set the predicted gain, wait until luma is stable, correct gain until luma = L_ref ± 3 %, then score D, ρ and the gain headroom on the same 8 frames.
5. **Accept the step** if all of these hold:
   - D ≥ **0.80** × D_ref;
   - ρ ≤ **1.5** × ρ_ref;
   - gain below maximum;
   - with the board in view: corner jitter ≤ j_max × reference and no corners lost.

   Thresholds are provisional (Dom, 2026-11-12) until the attended board run sets them (§6). j_max is set by that run as well.
6. **Stop** at the first failing step, keep the last passing one, and record why it stopped: `quality_D`, `quality_rho`, `gain_range`, `light` or `motion_unverified`.
7. **Lock and record** exposure, gain, L_ref, the D and ρ ratios, jitter, the reason and the timestamp, with the camera config and the calibration (D10–D12).

**Expected on 11-11/12's data** (provisional thresholds, matched luma about 140) [I from M]:
- **C922:** stops at −5 (its −6 step has D 0.78), so it is light-limited.
- **C930e:** about −7 to −8 (ρ ×1.9–2.3 at −9 fails).
- **Generic:** gain has no effect, so it stays at the shortest step that reaches luma at gain minimum.
- **Kiyo Pro:** unknown (11-11/12 was inconclusive).

The motion guard, the Kiyo Pro's linear probing and the settling rules below apply throughout.

#### Making it fast

Measured parts [M]:
- a control set returns in 1.7–5.6 ms, and the image changes 2–5 frames (92–191 ms) later (`W-PYMF-ALL.json` `pymf_streaming_set`);
- the Kiyo Pro was still settling more than 1 s after a gain set (`W-GAIN` rule probes);
- 8-frame probes repeated g_lim within 2–3 gain units over 10 runs (`W-GAIN` `forced_runs`);
- listing formats without opening a camera takes about 0.4 s (`W-FMT-NOGRAB`).

| technique | saves |
|---|---|
| all cameras in parallel, one pymf process (mid-stream exposure sets: yes on the Kiyo Pro and C930e; partial on the generic, only where the start was in auto; the C922 untested [M]) | the wall time is the slowest camera's, not the sum |
| **adaptive settling:** stop waiting once luma changes < 1 % over 3 frames; cap at 1.5 s; cache each camera's settle time | ≈ 150–250 ms per probe on the Logitech cameras instead of a fixed wait; the Kiyo Pro stays slow |
| score D and ρ on the same 8 frames used for luma | no separate scoring capture |
| **predict gain** from the camera's luma response (each exposure step needs about 2× luma; read the gain off the luma-vs-gain curve), then one correction | about 2 probes per step instead of about 8 for a binary search |
| **start near the answer** (from the cache, below): confirm the pair "step e passes, e−1 fails" instead of walking down from e0 | 2 steps checked instead of 3–6 |
| corner jitter (60 frames) only on that confirming pair | about 4 s instead of 2 s per step |
| skip gain on cameras where it has no effect (generic) | the whole gain search |
| skip the ceiling check when cached; watch delivered fps passively during the session and flag a drop | 1.5–4.5 s |

**Time per camera** [arith from the measured parts; to be checked in TP1]:

| situation | Logitech (C922, C930e) | Kiyo Pro |
|---|---|---|
| first time seen (cold) | ≈ 6–10 s (+ ≈ 4 s for corner jitter) | ≈ 15–25 s (+ ≈ 4 s) |
| seen before, same light (warm) | ≈ 0.5 s: apply the cached settings, one 8-frame check | ≈ 2 s |
| light changed by ≤ 1 stop | ≈ 1–3 s: re-tune gain at the cached exposure, check the neighbouring step | ≈ 4–8 s |
| scene changed or light changed > 1 stop | ≈ 3–6 s: search seeded from the cache | ≈ 8–15 s |

All cameras run together, so the whole rig takes as long as its slowest camera: about 20–30 s cold with a Kiyo Pro, under 1 s warm without one.

#### What to cache once a camera has been seen

**Key:** the stable camera key (serial where the camera has one, port path otherwise), plus firmware (bcdDevice) and the mode (size, fps, format). Any change in the key means a cold start. The cache is **learned on this machine for this device**, never shipped per model (D9). A cached value only *seeds* the search or skips a measurement that is re-checked passively; the final settings are always verified on the live image.

| cached item | depends on | how it's used | invalidated by |
|---|---|---|---|
| formats, control ranges, steps, defaults, which auto flags exist | device + firmware | skip the listing (≈ 0.4 s) | firmware change |
| exposure ceiling per mode (11-11/12: Kiyo Pro −7 @30) | device + mode | skip the ceiling check | a delivered-fps drop seen during a session |
| gain effect (none on the generic) | device | skip the gain search | firmware change |
| luma response: ratio per exposure step and the luma-vs-gain curve (normalised) | device + mode, roughly scene-independent [I] | predict gain: 1 probe + 1 correction | prediction off by > 20 % three times |
| settle time after an exposure set and after a gain set (max seen + margin) | device | adaptive-settling cap | a timeout |
| start-up quirks: resets at stream start (C930e: re-apply after the first frame), stall after a re-apply (Kiyo Pro about 300 ms: don't re-apply needlessly), auto-mode readback can't be trusted (generic), non-monotonic gain (Kiyo Pro: probe linearly) | device + firmware | what the step does after start and how it probes | firmware change |
| quality cost per stop of exposure traded for gain (D and ρ ratios at matched luma) | device + mode, partly scene [I] | predict the stopping step; start there and confirm the pair | the prediction misses by > 1 step |
| USB alt setting and load per mode (`mode_alt_cache.json`, 1.11) | device + mode | bandwidth check before start | firmware change |
| **last result:** exposure, gain, L_ref, D_ref, ρ_ref, jitter, the reason, time, plus a **scene fingerprint** (a 32×18 luma thumbnail of the reference frame) | device + scene + light | warm start: apply, check once | thumbnail correlation < 0.9 (scene moved), luma off by > 5 %, or a calibration with different locked values |

**Never cached:** the final luma, D and ρ check on the live image, the D10–D12 start values (read at every start), and anything about a Kiyo Pro that has wedged (the dead rule).

**During a session:** watch delivered fps (a drop means the ceiling is wrong) and median luma (a drift > 5 % means the light changed). Offer a quick re-tune between takes, never during a recording (§5.3).

### 5.3 How it runs
- **Once, before the session, with AE off.** It is triggered by the user (like today's RECOMMEND button) and never during recording.
  - The resulting exposure and gain are stored in the camera config.
  - On every later stream start they are **re-applied** (no new search). Since D14 (2026-11-12), a start also runs the one-probe warm check of §5.2b, and re-tunes from the cache only if luma or the scene fingerprint moved.
- **With the stream running.** The C930e and the generic reset controls at stream start, so the step runs after the first frame.
  - For the C930e, sets made ≥ 1 s after the first frame stick [M] ([W-AUTO.json](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO.json) `c930e_note`).
  - In the MF path, re-applying exposure at the first frame also worked: luma at −7 matched in 3/3 runs [M] (W-CTRL-EFFECT `fixed_controls.exposure.reapplied_at_0ms_ok`).
- **Settling per probe:** discard ≥ 200 ms of frames (≥ 6 at 30 fps), then take the median luma of 3 frames.
  - In-stream sets were visible within the suite's 150 ms guard [M] (`w_ctrl_effect.py:610-611`, segment start = set end + 150 ms, and the segment metrics changed as expected).
  - All cameras are probed in parallel. Roughly 12–15 probes × ~0.3 s ≈ 4–5 s total [arith].
- **Verification:**
  1. Read back exposure and gain: within one step, flags manual.
  2. Luma within the band (or the warning issued).
  3. Delivered fps within 1 % of requested. If not, step exposure down once and re-check: this catches cameras whose real exposure is longer than nominal.
  4. Re-check readback and luma after a stop/start (C930e).
- **Record** per camera, in the recording config / sidecar header: preset, ceiling, chosen exposure and gain (requested and read back), achieved luma, and any warning. Today the requested config is saved once per recording [C] (`skellycam/core/camera/opencv/opencv_helpers/opencv_extract_config.py:23`; review §3.5).
- **UI:** no gain control (rule 2026-11-11). The step may *show* the result read-only ("2.0 ms, gain boosted 40 %") and the add-light warning. Read-only display is compatible with "gain is not a separate control".

### 5.4 Per-camera rules

| Camera | Gain | Exposure | Re-apply | Other |
| --- | --- | --- | --- | --- |
| Kiyo Pro | min 0; limit measured (§5.2a). 11-11 evidence: noise jumps above 128 | −11…−2; luma responds weakly | after open; holds through start [M] | Found with brightness/contrast/backlight compensation non-default [M]. Decided (D11): lock them at their start values, record them, and ask the user on a calibration mismatch. Wedge handling as per plan |
| C922 | min 0; limit measured (§5.2a); 230 tested without a large jump | −11…−2 | holds through start [M] | Only 60 fps camera: verify −6 keeps 60 fps (§6, T4) |
| C930e | min 0; limit measured (§5.2a); 230 tested | −11…−2 | **apply both after the first frame (≥ 1 s) and verify**; resets at every start [M] | AE priority reads 1 [M]: set 0 (no effect in manual, but keeps the as-found AE sane) |
| generic 4c4a | ineffective and reset to 4 at start [M]; the measured rule leaves it alone | −7…3, **units unknown** [M, re-analysis] | — | Blur ceiling cannot be enforced until T3 measures real times. Until then use brightness only and flag "not suitable for fast motion" [I] |

The table records what each camera did on 11-11, as expectations for TP1. None of it is looked up at run time (D9). The C930e re-apply is handled generically: read back after the first frame (≥ 1 s) and re-apply anything that changed.

---

## 6. Tests to add to TP1 (question 6)

All run on the phase-1 MF backend, AE/AF/AWB off, fixed focus, MJPEG at the mode in use (and at 1080p where in scope). None was run for this study.

**T1. Temporal noise vs gain at equal brightness (per camera).**
- **Scene:** static, steady light (record it: lux and flicker if a meter is available). Include a matte grey card (flat ROI) and a printed chart with fine texture and a slanted edge (a ChArUco board works).
- **Grid:** gain at 0, 10, 25, 50, 75, 90, 100 % of the range (generic: every value 1–7). For each gain, the exposure step whose grey-card luma is closest to 110. Also a full grid, exposure −11…−5 × those gains, so the curves can be redrawn for any target.
- **Per cell:** re-apply after stream start (C930e ≥ 1 s), read back, wait 0.5 s, then save **64 consecutive frames** (not every third).
- **Compute:**
  - grey-card mean luma;
  - temporal σ per pixel across the 64 frames, averaged over the card. EMVA's two-frame method σ² = var(y₀ − y₁)/2 is a cross-check [S, EMVA §2.5];
  - the row-mean part of σ separately (flicker);
  - spatial non-uniformity from the 64-frame mean (high-passed) over the card;
  - detail: MTF50 from the slanted edge, plus gradient energy on the chart;
  - JPEG bytes (T2).
- **Dark frames:** lens covered, 64 frames per gain, for dark offset and dark σ (read noise in grey levels).
- **Validating §5.2b (D14, 2026-11-12; attended, ChArUco board on its stand, steady light).** Per camera, for every exposure step from the ceiling down, at matched brightness:
  - record corner jitter (px RMS over 60 frames), corner count, D and ρ;
  - find which of D and ρ predicts corner jitter on each camera;
  - set d_min, r_max and j_max where corner jitter starts to rise (provisional 0.80 / 1.5 / –);
  - time the cold and warm paths and check the cache rules (repeat after moving the board, i.e. a scene change, and after dimming the light by one stop);
  - run in a brighter scene than 11-11/12, with grid gains between 26 and 64.
- **Checking the in-step rule (D9; superseded by the item above):** T1's full grid is the reference for §5.2a. The reference cap per camera is the highest gain where, at target luma, σ_t ≤ 2 × σ_t at minimum gain **and** MTF50 ≥ 85 % of the minimum-gain value. Report the cap and the noise-vs-gain curve per camera. Then run the §5.2a measurement on the same scene, 10× per camera: pass if its g_lim lands within one probe step of the reference cap every time, and ρ rises monotonically with gain on the grid. Adjust the 1.5 / 0.85 / 3 % thresholds if not.

**T2. JPEG bytes per frame vs gain (same captures as T1).**
- Mean, p95 and max bytes per frame per cell. MB/s at 30 and 60 fps.
- Compare at equal luma (gain-heavy vs exposure-heavy cells).
- Check that delivered fps and frame integrity (strict decode) do not change with gain.
- Pass: bytes at the measured g_lim (or the T1 reference cap) ≤ 1.2 × bytes at minimum gain at equal luma (proposed threshold).

**T3. Real exposure time and blur vs exposure (also fills test plan M1, [test_gap_plan.md](test_gap_plan.md)).**
- **Target:** a rotating disk with a thin white radial line on black, at a known speed (record turntable at 33⅓ or 45 rpm, or a motor with a tachometer). The camera faces the disk; light is steady and bright enough for −11 at moderate gain.
- **Settings:** exposure −11…−4 (generic: −7…3), gain fixed. Save 30 frames each.
- **Measure:** the arc length of the smeared line at radius r. Exposure time t = arc angle ÷ ω.
- **Report:** measured t vs nominal 2^v per camera. This also gives the generic's real exposure scale. Blur px = ω·r·t·px_per_m: confirm §3.2's arithmetic within 20 %.

**T4. Frame-rate ceiling.**
- For every exposure step at each in-scope rate (30 fps on all cameras; 60 fps on the C922, and any 60 fps mode on the Kiyo), stream 5 s and compute delivered fps from device/sample timestamps.
- Pass: fps within 1 % of nominal for every step ≤ the frame-period ceiling (−5 at 30 fps, −6 at 60 fps).
- Report the first step that lowers the rate: today −4 at 30 fps → 16.0 / 16.0 / 19.4 fps [M, re-analysis].

**T5. The exposure step end to end.**
- **Conditions:** three light levels (bright, room, dim), measured. Each motion preset × 30 and 60 fps.
- **Check:**
  - chosen exposure ≤ ceiling; gain ≤ the measured g_lim (generic: g_lim = minimum, gain left alone);
  - luma in band, or the add-light warning fires (and it must fire in dim);
  - readbacks match; fps holds;
  - settings re-applied and verified after stop/start (C930e) and close/reopen;
  - constant for 10 minutes (shared with TP1 "Auto stays off");
  - step duration per camera and for all cameras in parallel.

---

## 7. What could not be determined

- **Real exposure times.** All times are nominal 2^v. The only hints are the fps drops at −4: C922 and C930e ≈ 62.5 ms, Kiyo ≈ 50 ms. The generic's exposure units are unknown. Needs T3.
- **How UVC gain values map to dB, and where analog becomes digital,** for any of our cameras. Not published [S: vendor-defined]. Only the Kiyo's sensor (IMX327) has a public gain spec, and that identification is press-sourced [W].
- **Read noise and fixed-pattern noise.** No dark frames exist; the temporal differences do not measure fixed patterns.
- **Why the Kiyo's luma responds so weakly to exposure and gain:** its non-default brightness/contrast/backlight settings, ISP tone mapping, or HDR. Unknown.
- **Whether the C922's AE adds unreported gain.** Inferred from luma only.
- **Whether −6 holds 60 fps** on the C922 (manual exposure at 60 fps was never measured).
- **The generic camera's lowest-noise gain.** Gain 1 was never tested. Gains 2/4/6 gave flat-area noise 1.26 / 1.13 / 1.47 with no change in luma: not monotonic, so there is no clear lowest-noise value.
- **Effect of noise at our levels (≈1–2 grey levels after JPEG) on MediaPipe / RTMPose keypoints or on ChArUco corner accuracy.** No published evidence found.
- **Limits of the noise numbers here.** One static evening scene, AF and AWB on, 4–13 saved frames 100 ms apart per segment, brightness matched only within 3–10 %. Treat them as direction and rough size, not as camera specifications. T1 replaces them.

---

## Appendix A. How the noise and size numbers were computed

- **Inputs:** W-CTRL-EFFECT exposure and gain runs, 4 cameras × MF and DS paths × 3 runs × 3 segments = 144 segments.
  - Saved frames (every 3rd frame) and per-frame byte counts are under `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z\W-CTRL-EFFECT\<camera>\<path>_<control>_r<N>\` (`frames.jsonl`, `frames.mjpeg`). This is outside the repo, with the size of rebuildable raw data.
  - Run metadata (set times, values, readbacks) comes from [W-CTRL-EFFECT.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json).
- **Segment bounds:** the same rule as the suite [C] (`research/usb_cameras/suite/windows/tests/w_ctrl_effect.py:294-320, 605-613`).
  - DS: from fix0's end + 150 ms, then each in-stream set's end + 150 ms, to the next set's start.
  - MF: the `applied_qpc_ns` of the scheduled sets.
  - Only the second half of each segment is used (the "settled" half, as in the suite).
  - The recomputed luma matches the suite's `metric_values` within 0.04 grey levels in all 144 segments (check of the re-analysis).
- **Luma:** the Y of the decoded JPEG (PIL, "L"), or the Y plane of raw YUY2 (Kiyo DS), over the central 80 % ROI.
- **Temporal noise:**
  - for consecutive saved frames (100 ms apart), the standard deviation of the difference image ÷ √2 (EMVA's two-frame idea [S]);
  - only over **flat** pixels: Sobel gradient magnitude of the segment-mean frame, box-blurred 9×9, < 6 grey levels, and mean luma 8–247. This excludes edges, where focus hunting (AF was on) and sub-pixel shifts dominate frame differences. Unmasked noise was 1.0–13.6× the flat-area value (median 3.1×) for that reason;
  - also reported in luma bins (20–60, 60–100, 100–140, 140–180, 180–230), each with ≥ 2000 flat pixels;
  - a row-mean-removed variant (flicker check, computed on the unmasked difference in a first pass) differed from the plain value by ≤ 4 %.
- **Detail:** mean absolute horizontal difference of the segment-mean frame.
- **Bytes:** mean `bytes` over all frames in the settled half (all frames, not only the saved ones). The generic camera's first MF segment had small frames on every control (44–57 kB vs ~100 kB on DS). This looks like a start-up effect, so it was excluded from comparisons.
- **The script** was a one-off in the session scratchpad. A copy is kept in [`tools/exposure_rescore/gain_noise.py`](../tools/exposure_rescore/gain_noise.py) (2026-11-11). Re-running needs only numpy, Pillow and OpenCV and the paths above.

---

## Sources (all accessed 2026-11-11)

- **[S]** EMVA 1288 Release 4.0 Linear (2021). https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf (§2.4 noise model, §2.5 two-frame method, §2.6 SNR)
- **[S]** Microsoft, KSPROPERTY_CAMERACONTROL_EXPOSURE. https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-exposure
- **[S]** Microsoft, KSPROPERTY_CAMERACONTROL_AUTO_EXPOSURE_PRIORITY. https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-auto-exposure-priority
- **[S]** Microsoft, KSPROPERTY_VIDEOPROCAMP_GAIN. https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-videoprocamp-gain
- **[S]** libuvc `standard-units.yaml` (UVC control semantics: AE modes, AE priority, 100 µs absolute exposure units, gain). https://raw.githubusercontent.com/libuvc/libuvc/master/standard-units.yaml (a transcription of the UVC definitions; the USB-IF UVC PDF itself was not read)
- **[S]** Sony, IMX327LQR/LQR1 Product Information v1.3 (mirror). https://www.1stvision.com/cameras/sensor_specs/IMX327.pdf
- **[S]** Basler product documentation, Gain. https://docs.baslerweb.com/gain
- **[S]** Basler product documentation, Auto Function Profile. https://docs.baslerweb.com/auto-function-profile
- **[S]** Wang et al., "When Human Pose Estimation Meets Robustness: Adversarial Algorithms and Benchmarks", CVPR 2021. https://arxiv.org/pdf/2105.06152
- **[S]** Hendrycks & Dietterich, ImageNet-C corruption code. https://raw.githubusercontent.com/hendrycks/robustness/master/ImageNet-C/imagenet_c/imagenet_c/corruptions.py
- **[S]** Hu et al., "Deep ChArUco: Dark ChArUco Marker Pose Estimation", CVPR 2019. https://ar5iv.labs.arxiv.org/html/1812.03247
- **[W]** Tom's Hardware, Razer Kiyo Pro review (sensor named as Sony IMX327). https://www.tomshardware.com/reviews/razer-kiyo-pro-webcam-review-a-new-hardcore-standard
- **[W]** libcamera-devel, "controls: Updates to gain and exposure controls" (UVC gain has no units). https://lists.libcamera.org/pipermail/libcamera-devel/2020-April/008169.html
