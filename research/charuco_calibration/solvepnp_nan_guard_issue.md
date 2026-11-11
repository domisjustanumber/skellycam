# Calibration: `len(corners) < 6` guard passes all-NaN ChArUco rows, so `solvePnP` runs on empty frames

> Draft freemocap issue, written 2026-11-06, not yet posted. Source: the calibration speed review in freemocap session `9518d93c` (quick win 4). Full plan with measurements: freemocap `plans/calibration-qw4-solvepnp-empty-rows.md` (local, uncommitted). Re-checked against freemocap `development` @ `5632778a` on 2026-11-06: the bug is still present.

## Summary

`estimate_pose_points` (`freemocap/core/tasks/calibration/charuco_board/charuco_board_ops.py`) is meant to skip board pose estimation unless at least 6 ChArUco corners were detected. The check is `len(corners) < 6`, but frames with no detection never fail it:

- skellytracker's `anipose_export.py` (L58–64) turns an empty frame into a row whose `corners` is an `n_corners × 1 × 2` array of all NaN, with `ids` listing **every** corner id.
- So `len(corners) == n_corners`: 24 on the 7x5 board, 8 on the 5x3 board. Both are ≥ 6, so the row goes on to `cv2.solvePnP`.
- With NaN image points, OpenCV 4.12 returns `ret=True` and a NaN rvec/tvec. That NaN pose is stored as if it were a valid pose.

## Impact

- **Wasted time.** Each empty row costs about 0.77 ms in `solvePnP`, roughly 3× a real solve. On the test recording 82% of rows are empty (543 of 666). Pose estimation takes 0.46 s at 222 frames and 4.6 s at 2,220 frames, and accounts for about 66% of solver wall time.
- **Misleading log.** `bundle_adjust.py` counts `rvec is not None`, so it logs "219/222 frames have valid board pose" when the true counts are 31, 30 and 52 per camera.
- **Hidden NaN path.** Any single NaN in a row produces a NaN pose. The exporter can't create partially-NaN rows today, but nothing enforces that.
- **Results are not affected.** Downstream code treats a NaN pose the same as `None` for empty rows, so calibration output is correct today.

## Steps to reproduce

1. Run anipose posthoc calibration on any recording that has frames where the board isn't visible (for example the standard test recording).
2. Look at the "valid board pose" log line: it counts nearly every frame.
3. Or call `estimate_pose_points` directly with `corners=np.full((24,1,2), np.nan)` and `ids=np.arange(24)`. It calls `solvePnP` and returns NaN arrays where it should return `(None, None)`.

## Proposed fix

In `estimate_pose_points`:

1. Count **finite** corners and return `(None, None)` if there are fewer than 6.
2. Filter `ids` and `corners` down to the finite entries before calling `solvePnP`.
3. Treat a non-finite rvec/tvec from `solvePnP` as "no pose".

```python
img_points = np.asarray(corners, dtype=np.float64).reshape(-1, 1, 2)
flat_ids = np.asarray(ids).ravel()
finite = np.isfinite(img_points[:, 0, :]).all(axis=1)
if np.count_nonzero(finite) < 6:
    return None, None
if not finite.all():
    img_points, flat_ids = img_points[finite], flat_ids[finite]
...
if not ret or not (np.isfinite(rvec).all() and np.isfinite(tvec).all()):
    return None, None
```

**Don't** fix it by dropping empty rows in `CharucoObservationAggregator.to_anipose_rows`. That would change `charuco_frames` and the reported `n_observations_used` (666 → 102 on the test recording), and break the "0 of 3" message in `test_calibration_diagnostics`.

## Validation already done

- **Same results as before:** old vs new code with fixed seeds (5 seeds at 222 frames, 1 at 2,220 frames). Camera parameters, BA error, `n_observations_used` and all intermediate arrays matched exactly.
- **Speed:** pose stage 0.46 s → 0.035 s (222 frames) and 4.61 s → 0.34 s (2,220 frames). Whole `calibrate_cameras_from_rows`: 1.14 s → 0.69 s and 6.17 s → 1.80 s.
- **Log:** the valid-pose counts become the true values (31 / 30 / 52).
- **Branches:** reproduces on both `development` (5632778a) and `development-streaming` (c27fc29); the affected files are identical on both.

## Tests to add

Add `freemocap/tests/calibration/test_charuco_pose_guard.py` covering:

- an all-NaN row returns `(None, None)` without calling `solvePnP`;
- an empty row built by the real exporter returns `(None, None)`;
- rows with fewer than 6 finite corners, and zero-length rows, return `(None, None)`;
- a partially-NaN row gives the same pose as its finite subset;
- a clean row recovers a known pose;
- non-finite `solvePnP` output returns `(None, None)`;
- `estimate_pose_rows` marks only solvable rows.

## Out of scope

Switching to `SOLVEPNP_IPPE` was evaluated separately. Raw IPPE changes the BA result in no consistent direction and returns NaN on collinear corners, so it should be a separate, validated follow-up.
