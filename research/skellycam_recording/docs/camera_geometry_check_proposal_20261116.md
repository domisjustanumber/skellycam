# Proposal: resolving an identical camera on a new port by calibration geometry (freemocap)

## 0. Headline

The check already exists in freemocap. `GEOMETRY` is a working observation-based matcher, wired into both the realtime and the post hoc paths. The work is to close four gaps, not to build a matcher:

1. **A plausible wrong binding is accepted without contrast.** The supplied binding is accepted as soon as it passes absolute error ceilings, with no comparison against the swapped alternative. My simulation says a swapped two-camera rig with the subject standing at the convergence point passes those ceilings.
2. **Post hoc processing can silently use a bad search winner.** Under the default "continue" policy, a `POOR` or `AMBIGUOUS` result still hands the search winner to triangulation.
3. **Nothing reaches the user.** The only output is a per-camera `match_kind` on the wire that no UI component reads, plus log lines.
4. **The matcher knows nothing from the capture side.** It has no notion of which cameras are ambiguous or which pairing the user confirmed.

Nothing was edited, created, checked out or run against a camera. Two numpy-only simulations were piped to Python on stdin.

Marks: **[C]** = read in code at `c27fc299` (path:line, repo `c:\Users\Dom\GitHub\freemocap\freemocap`), **[S]** = `c:\Users\Dom\GitHub\freemocap\skellyfileformat\spec\SPEC.md`, **[A]** = my own analysis, **[Sim]** = my simulation (my own DLT, not freemocap's `Triangulator`).

`upstream/development-streaming` is `c27fc299`; `upstream/sfn26` is `ca0c17cc`. Between them, `matching_models.py`, `matching_evaluation.py`, `matching_fitness.py` and `matching_search.py` are unchanged. `live_matching.py`, `observation_sampling.py`, `posthoc_matching.py` and `calibration_state.py` differ only in plumbing (`apply_matching` returns a "changed" flag; observation arrays are vectorised).

## 1. What exists today

All paths below are under `freemocap/core/tasks/calibration/` unless a fuller path is given.

**Binding by label**
- `bind_calibration_to_live_cameras` is pure and all-or-nothing: pass 1 exact id, pass 2 structured index, else `UNMATCHED`. [C] `shared/calibration_camera_binding.py:108-232`
- Its docstring anticipates "the scored permutation search that will eventually replace the index pass". [C] `shared/calibration_camera_binding.py:24-26`
- It is called from `CalibrationStateTracker.bind_live_cameras`, memoised on (calibration generation, live id and index set). [C] `shared/calibration_state.py:215-262`

**`GEOMETRY` is implemented**
- The enum value means "assignment passed observation-based geometry fitness checks". [C] `shared/calibration_camera_binding.py:44-45`
- It is set in `CalibrationStateTracker.apply_matching` when a matching result is `INITIAL_ACCEPTED` or `MATCHED`. Other statuses keep the current binding under the continue policy, or raise under stop. [C] `shared/calibration_state.py:181-204`

**The matcher (`camera_matching/`)**
- **Fitness:** triangulate all points with the hypothesised cameras, reproject, and require positive depth in every camera. Errors are in pixels scaled to a 1000-pixel image diagonal. Points whose rays are separated by less than `minimum_ray_angle_degrees` are dropped. [C] `matching_fitness.py:19-37, 40-100`
- **Acceptable** means, for every camera: valid fraction ≥ 0.9, median ≤ 2.0, p90 ≤ 5.0. [C] `matching_fitness.py:84-89`, defaults `matching_models.py:21-31`
- **Cost formula:** per point, `min((sum over cameras of e²) / n_cameras_seeing / maximum_p90_error², 1)`; per frame, the mean over shared points; `mean_cost` is the mean over frames. A point behind a camera has infinite error, so cost 1. [C] `matching_fitness.py:90-99`
- **Evaluation order:**
  - If the initial assignment is acceptable on both alternating-frame halves, return `INITIAL_ACCEPTED` with no search. [C] `matching_evaluation.py:64-70`
  - Otherwise build a two-view cost for every supported source pair and every ordered camera pair, then search. [C] `matching_evaluation.py:72-81`
  - `AMBIGUOUS` when best and runner-up are closer than `minimum_score_gap` (0.05) on either half. [C] `matching_evaluation.py:92-102`
  - `POOR` when the winner's full-rig fitness on the held-out half is not acceptable; the winner is still returned as `assignment`. [C] `matching_evaluation.py:103-105`
- **Search:** exact branch and bound over injective assignments, keeping the best two, with a node cap of 250,000. [C] `matching_search.py:12-71`
- **Supported edges:** a source pair needs ≥ 6 frames with ≥ 6 shared points in each half, and the edge graph must be connected, else `INSUFFICIENT`. [C] `matching_evaluation.py:19-32`
- **Only hard prior:** image size equality. [C] `matching_models.py:176-177`

**Realtime path**
- The aggregator merges each camera's skeleton and ChArUco observations per frame and feeds `LiveGeometryMatcher.update` every frame when triangulation is enabled. [C] `freemocap/core/pipeline/realtime/realtime_aggregator_node.py:862-890`; constructed at `:453`
- The matcher samples every 0.2 s into a 24-sample window (about 5 s), takes the label binding as the initial assignment, and runs in a one-thread executor. [C] `camera_matching/live_matching.py:24, 55-89`
- Frames with more than one bounding box are skipped. [C] `camera_matching/live_matching.py:53-54`
- Samples must share one `frame_number`. [C] `camera_matching/observation_sampling.py:51-52`
- It keeps re-running after success (`MONITORING`). It stops (`SUSPENDED`) after `AMBIGUOUS`, `POOR` or `SEARCH_LIMIT`; only `INSUFFICIENT` keeps collecting. [C] `camera_matching/matching_lifecycle.py:45-59`

**Post hoc path**
- `PosthocMatchingRequest.evaluate` samples up to 24 frames evenly; the initial assignment is identity when source ids equal calibration ids. [C] `camera_matching/posthoc_matching.py:35-60`
- It is called from `freemocap/core/tasks/mocap/posthoc_mocap_task.py:197-205` and `freemocap/core/pipeline/dataflow/scientific_recording.py:293-297`.
- `resolve` uses `result.assignment` for triangulation unless the policy is stop. [C] `camera_matching/posthoc_matching.py:17-25, 62-64`

**Data available at bind time**
- Per camera: id, index, image size, intrinsics, extrinsics. [C] `shared/camera_model.py:18-24`
- Calibration metadata: board definition, reprojection error, observation counts. [C] `shared/calibration_metadata.py:18-25`
- The TOML also carries `source_take_uuid` and `controls_at_calibration`. [S] :1405, :1479
- The calibration take's 2D board observations are not in the TOML. The spec puts them in that take's Parquet [S] :1686-1689; I did not confirm that the calibration task persists them.

**Live data**
- Per camera and frame: `skeleton_observation` and `charuco_observation`. [C] `freemocap/pubsub/pubsub_topics.py:81-82`
- Point names are stage-prefixed (`body.nose`, `charuco.CharucoCorner-0`). [C] `shared/calibration_state.py:48-55`
- The matcher takes the 64 best-shared names. [C] `camera_matching/observation_sampling.py:12-26`

**Reusable geometry code**
- `Triangulator.triangulate`, `.project`, `.signed_reprojection_error`, `.mean_reprojection_error`. [C] `freemocap/core/tasks/triangulation/triangulator.py:136, 167, 546, 568`
- `evaluate_geometry_fitness` (above). There is no epipolar or Sampson code.

**Outputs today**
- **Wire:** per-camera `match_kind` and `calibration_camera_id`. [C] `freemocap/api/websocket/websocket_server.py:219-230`; schema includes "geometry" at `freemocap-ui/src/services/server/transport/message-contract.ts:69, 84`
- **UI:** no file under `freemocap-ui/src/components` or `src/store` reads `match_kind` (grep empty). Only two settings exist: auto-match on/off and the failure policy. [C] `freemocap-ui/src/types/camera-matching.ts:6-14`
- **Recording:** `camera_assignment` `{status, source_to_calibration, fitness, error_units}` goes into the Parquet descriptor's processing block. [C] `freemocap/core/pipeline/dataflow/scientific_recording.py:42-50`, `freemocap/core/recording/result_processing/observation_publication.py:163-166`; already in the spec part `skellyfileformat/spec/parts/parquet-descriptor.md:214`
- **Manifest:** the per-camera `calibration_camera` member exists [S] :725; no matching warning code exists [S] :759-763, :2289-2292.

**Tests**
- Seven matching test files exist under `freemocap/tests/calibration/`. The synthetic rig is three cameras with identity rotations. [C] `freemocap/tests/calibration/test_matching_fitness.py:19-32`
- Permutation recovery is tested. [C] `freemocap/tests/calibration/test_matching_evaluation.py:31-36`
- I did not run them.

## 2. The proposed check

### Signals

| Signal | Verdict | Reason |
|---|---|---|
| (a) Multi-view consistency of named 2D points (person or board) | **Recommended; it is what exists** | Triangulate, reproject, and check depth sign. |
| Sampson / epipolar error instead of reprojection | Not recommended | It has no depth sign. For near-parallel pairs the epipolar constraint is exactly swap-symmetric, and only depth sign separates the hypotheses (toe-in 6° or less in [Sim]). |
| (b) Board pose per camera (PnP), compared as relative poses | Defer; diagnostic only | Works from one frame and gives degrees and millimetres, which helps tell "moved" from "swapped". But board corners already enter (a) as named points with no new code, and planar PnP is unstable for small frontal boards. |
| (c) Current view against the calibration take | Defer; the only signal for the cases (a) cannot solve | Matching static background features against a calibration-take frame works for symmetric rigs, cameras with no shared view, and without a person. It needs the take's videos still on disk, a new image path, and tolerance to lighting and furniture changes. Comparing 2D board observations is useless because the board moves. |
| (d) Intrinsics alone | Useless for identical models | Unit-to-unit differences (about 1% focal length, some pixels of principal point) are below what can be estimated live without a fresh board calibration. Image size is already a hard filter. [A] |

### Changes to (a)

**Inputs.** `CameraMatchingRequest` gains one optional field, `candidate_cameras`: for each source, the set of calibration camera indexes it may be.
- A one-element set marks an unambiguous camera (serial or stored locator matched).
- The capture side fills the ambiguous sets with same vendor and model candidates.
- A second optional field, `user_confirmed_sources`, names sources whose pairing the user picked.
- `compatible()` gains the candidate test beside the image-size test, so disallowed pairs get infinite cost and the existing search prunes them.

**Contrast rule (the main fix).** When any source has more than one candidate, do not return `INITIAL_ACCEPTED` on absolute fitness alone. Always score the alternatives inside the candidate sets and require the same gap rule the search uses.

**Outputs.** Existing statuses, no new enum values:

| User-facing outcome | Status | Condition |
|---|---|---|
| Confirmed | `INITIAL_ACCEPTED` | Initial is acceptable and beats every alternative by the gap on both halves |
| Different pairing suggested | `MATCHED` with assignment ≠ initial | Winner acceptable and ahead by the gap |
| Cannot tell | `AMBIGUOUS` or `INSUFFICIENT` | Gap too small, or evidence missing or disconnected |
| Calibration does not fit | `POOR` | No assignment is acceptable. Never reported as a swap |

`CameraMatchingResult` already carries the fitness and best/runner-up costs needed for the message.

**Search cost.** [A]
- The pair-cost table needs (supported edges) × N × (N−1) two-view fitness calls on 12 frames × up to 64 points. For 8 cameras that is at most 28 × 56 = 1,568 calls.
- A full 8-camera tree is 109,600 nodes, under the 250,000 cap, so it always completes.
- With anchors fixed, an ambiguous subset of k costs k! leaves (2, 6, 24 for k = 2, 3, 4).
- Wall-clock time is not measured.

**Minimum data.** Keep the existing gates [C] `matching_models.py:21-31`:
- `minimum_frames` 6 per half, `minimum_points_per_frame` 6, `minimum_point_visibility` 0.5, `minimum_ray_angle_degrees` 1.0.
- Every ambiguous camera needs a supported edge to at least one other camera.

Coverage matters more than count [Sim]: a subject parked at the point both cameras look at gives almost no contrast. I propose no separate coverage parameter; the gap rule already turns low coverage into "cannot tell", and the UI then asks the user to walk through the volume or wave the board.

**Decision parameters.**

| Parameter | Start value | Status | Tuning |
|---|---|---|---|
| `maximum_median_error` | 2.0 | existing | Set near the 99th percentile of healthy takes in replay. In [Sim], 6 px tracker noise on 1280×720 puts the true assignment at median about 2.0, so this ceiling may be too tight for person keypoints. |
| `maximum_p90_error` | 5.0 | existing | Same replay. |
| `minimum_valid_fraction` | 0.9 | existing | Leave. |
| `minimum_score_gap` | 0.05 | existing | Choose so that fewer than 1 in 1,000 replay windows suggests a wrong swap. |
| `contrast_window_maximum_frames` | 120 (about 24 s) | new | On `AMBIGUOUS`, keep collecting up to this many samples before reporting "cannot tell". Today `AMBIGUOUS` suspends. |
| `suggestion_agreeing_windows` | 2 | new | Consecutive windows that must agree before a different pairing is shown. |

**What is shown and applied.**
- **No prior binding (the "identical camera on a new port" case, label binding `UNMATCHED`):** apply the geometry result, mark the camera "matched by geometry", and tell the user. This is what the live path does today, minus the telling.
- **Result contradicts an applicable binding or a user pick:** do not install it. Show "geometry suggests camera X and camera Y are exchanged" with both previews and the two costs, and let the user confirm. On confirmation, freemocap asks the capture side to rebind the remembered keys. That is the "these two are swapped" action the design study calls for (`c:\Users\Dom\GitHub\freemocap\skellycam\research\skellycam_recording\docs\camera_user_labels_design_20261116.md:108`).
- **Post hoc:** under `POOR`, `AMBIGUOUS` or `SEARCH_LIMIT`, triangulate with the label binding when one exists, not the search winner. Today the winner is used. [C] `camera_matching/matching_evaluation.py:103-105` with `camera_matching/posthoc_matching.py:17-25`

## 3. Failure modes and limits

**Two cameras, swapped.** [A]
- Let the calibrated relative pose be T (camera A to B), with essential matrix E. The swapped hypothesis tests the data against Eᵀ, which is the essential matrix of T⁻¹.
- So a swap is undetectable by any geometric test exactly when T = T⁻¹: the two cameras are related by a half-turn about a line, with identical intrinsics.
- **Facing each other, both upright:** this is that case. [Sim] gives identical scores for both hypotheses.
- **Parallel side-by-side pair:** E is antisymmetric, so the epipolar test cannot tell, but every swapped point triangulates behind the cameras. The existing depth check catches it (valid fraction 0 in [Sim]).
- **Usual toed-in pair:** not symmetric (the swapped rig diverges), so it is identifiable in principle, but weakly when the subject sits at the convergence point.

[Sim] for the toed-in pair (1.5 m baseline, 900 px focal length, median / p90 in the code's units):

| Scene | True | Swapped | Passes the 2.0 / 5.0 ceilings swapped? |
|---|---|---|---|
| Person standing at 3 m, toe-in 8°, 4 px noise | 1.29 / 3.12 | 1.92 / 4.98 | Yes |
| Person walking a 2 × 2 m area, toe-in 12° | 1.25 / 3.12 | 5.74 / 19.18 | No |
| 0.3 m board held at centre, toe-in 12°, 1 px noise | 0.31 / 0.74 | 0.35 / 0.92 | Yes |
| Board waved through the volume, toe-in 12° | 0.35 / 0.82 | 3.12 / 10.14 | No |
| Facing pair, 0.3 m and 3° off symmetric, 2 px noise | 0.67 / 1.59 | 8.89 / 21.36 | No |

A swapped pair with a centred subject would therefore be `INITIAL_ACCEPTED` today. The contrast rule fixes the standing-person case (the cost gap is clear) and returns "cannot tell" for the small centred board.

**Symmetric larger rigs.** [A] A relabelling is undetectable only when a rigid motion maps the whole rig onto itself. Four upright cameras on a square have quarter-turn symmetries, but those move all four. A swap of two cameras with the others fixed as anchors is not a symmetry, because the required half-turn would put the cameras upside down. Mirror-symmetric rigs are not degenerate for the same reason: cameras do not mirror. Real rigs are only near-symmetric, so detectability scales with asymmetry over noise.

**Other limits.**
- **No shared field of view:** the evidence graph is disconnected, so the result is `INSUFFICIENT` forever [C] `camera_matching/matching_evaluation.py:26-32`. Only signal (c) or the user can resolve it.
- **Rig moved since calibration:** no assignment fits, so the result is `POOR`. Report "calibration no longer fits these cameras", never a swap. A swap is claimed only when an alternative is acceptable with the gap.
- **One camera moved and re-plugged:** every pair touching it scores badly under every candidate while the rest agree. The pair-cost table already holds this; attributing it to one camera is a deferred nicety.
- **Focus or zoom change:** looks the same as "moved" for that camera. Same report.
- **Too few detections:** `INSUFFICIENT`; collection continues.
- **Unsynchronised frames, rolling shutter, fast motion:** errors rise equally for all hypotheses, so the risk is a false `POOR`, not a false swap. A sync error of 16 to 33 ms on a hand moving 1 to 2 m/s is 10 to 20 px at 3 m [A]. Mitigation is the prompt ("walk slowly"), not code, in the first version.
- **Several people:** frames are skipped.
- **Left/right flips by the tracker:** point names are trusted as identity. These add outliers to all hypotheses.

## 4. Where it fits

| Moment | State | What to do |
|---|---|---|
| Calibration loaded or bound | Exists (matcher resets on calibration generation change, [C] `camera_matching/live_matching.py:32-37`) | Pass candidate sets |
| Capture side reports an ambiguous or user-confirmed camera | New | Reset the matching lifecycle and pass `candidate_cameras` and `user_confirmed_sources` |
| Continuous monitor during a session | Exists (`MONITORING`) | Surface a status change |
| Recorded take, after the fact | Exists on every post hoc run | Fix the "continue" behaviour; add the warning |

**Reports to the user.** One realtime message per calibration binding: status, current pairing, suggested pairing, costs of best and runner-up, per-camera median and p90. The UI shows a badge per camera (matched by label, matched by geometry, unverified, suggestion pending) and the confirm dialog.

**Record.**
- `camera_assignment` in the Parquet descriptor already holds status, pairing and fitness.
- Candidate manifest warning codes with source `freemocap`: `camera_assignment_changed` (processing used a pairing different from the `camera_key` link) and `camera_assignment_unverified` (ambiguous cameras, check could not decide). Each carries the `camera_key`.

**What the spec would need.**
- The two codes in the take-warning list and in SFF-727.
- A rule for which link wins when the manifest's `calibration_camera` names a different table than `camera_key` does. SFF-815 says readers link by `camera_key` only.
- A note on SFF-837: a geometry-reassigned run compared "by `camera_key`" will raise `calibration_mismatch`. That should be either intended or excluded.

## 5. Test plan

**Synthetic (no hardware).** Extend the existing fixture into a rig set: toed-in pair swept 0° to 30°, facing pair exact and perturbed, square of 4, ring of 8, and one camera with no overlap. For each: project points with `Triangulator.project`, permute labels, add 1 to 8 px noise, vary coverage (centred versus volume-filling). Assert the status table of section 2, including:
- the centred-subject swapped pair is not accepted;
- the exact facing pair returns "cannot tell";
- a moved-camera rig returns `POOR` with no swap suggestion.

**Replay (no hardware).** Take existing recorded takes with stored 2D observations and exchange dictionary keys between two sources before `PosthocMatchingRequest.evaluate`; no re-tracking or video decoding is needed. Collect true and swapped costs per window across takes, then set `minimum_score_gap` and the two ceilings from those distributions. Also replay a take against a calibration from a different session to exercise "does not fit".

**Hardware adds.** Real sync error and rolling shutter, real tracker noise and left/right flips, two identical serial-less cameras actually re-plugged and cable-swapped, and the prompt and confirm flow with the capture side.

## 6. Effort and order

**Smallest useful first version** (all in existing files):
1. Contrast rule plus `candidate_cameras` in `matching_models.py` and `matching_evaluation.py`.
2. Post hoc: keep the label binding on `POOR`, `AMBIGUOUS` and `SEARCH_LIMIT`.
3. `AMBIGUOUS` keeps collecting instead of suspending (`matching_lifecycle.py`).
4. Do not auto-install a result that contradicts an applicable binding; publish status and suggestion on the wire.
5. Synthetic rig tests and the replay script for thresholds.

**Then:** the UI badge and confirm dialog, the manifest warning, and the capture-side rebind call.

**Defer:**
- A preflight that predicts from the calibration alone which swaps are indistinguishable (same projection trick as the tests).
- Per-camera "moved" attribution.
- Board-pose diagnostic (b).
- Background-appearance signal (c).
- A motion-speed gate.

## Not verified

- I did not run freemocap's tests or measure matcher run time.
- [Sim] uses my own two-view DLT, identical intrinsics, Gaussian noise and box-shaped point clouds. It indicates the risk; it does not prove behaviour of the real code or tracker.
- I read `upstream/sfn26` only as a diff of the calibration folder; its aggregator call is at a different line (about 850).
- I did not trace how live camera ids relate to `camera_key` on these branches, or whether the calibration take's board observations are saved by the calibration task.
- The claim that no UI component reads `match_kind` rests on a grep of `freemocap-ui/src/components` and `src/store` at `c27fc299`.

Skipped: sections 2 to 6 are a design, not tested code; thresholds are starting values until the replay is run. Risk to know now: on the default "continue" policy, post hoc processing today can relabel cameras to a poorly fitting search winner without telling anyone.
