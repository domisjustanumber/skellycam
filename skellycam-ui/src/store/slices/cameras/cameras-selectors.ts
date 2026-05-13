// cameras-selectors.ts
import {createSelector} from '@reduxjs/toolkit';
import {RootState} from '../../types';
import {
    Camera,
    CameraConfig,
    cameraMatchesListedVirtualPattern,
    DEFAULT_UI_FRAMERATE,
    formatsIncludeTargetFramerate,
    fpsValuesEquivalent,
    uniqRepresentativeFpsFromFormats,
} from './cameras-types';

// ========== Basic Selectors ==========
export const selectCameras = (state: RootState) => state.cameras.cameras;
export const selectIsPaused = (state: RootState) => state.cameras.isPaused;
export const selectIsLoading = (state: RootState) => state.cameras.isLoading;
export const selectIsDetectingCameras = (state: RootState) => state.cameras.isDetectingCameras;
export const selectSuppressListedVirtualCameras = (state: RootState) =>
    state.cameras.suppressListedVirtualCameras;
export const selectHardwareEnumerationChanged = (state: RootState) =>
    state.cameras.hardwareCameraEnumerationChanged;
export const selectError = (state: RootState) => state.cameras.error;

/** Devices shown in sidebar / FPS logic: listed virtual cameras are omitted while “Ignore virtual webcams” is on. */
export const selectCamerasDisplayedInUi = createSelector(
    [selectCameras, selectSuppressListedVirtualCameras],
    (cameras, suppress): Camera[] =>
        (suppress ? cameras.filter((c) => !cameraMatchesListedVirtualPattern(c)) : cameras),
);


// ========== Derived Selectors ==========
export const selectCameraById = createSelector(
    [selectCameras, (_: RootState, cameraId: string) => cameraId],
    (cameras, cameraId) => cameras.find(cam => cam.id === cameraId)
);

export const selectSelectedCameras = createSelector(
    [selectCamerasDisplayedInUi],
    (cameras) => cameras.filter((cam) => cam.selected),
);

export const selectHasCameraSelection = createSelector(
    [selectSelectedCameras],
    (selected) => selected.length > 0,
);

export const selectConnectedCameras = createSelector(
    [selectCamerasDisplayedInUi],
    (cameras) => cameras
        .filter((cam) => cam.connectionStatus === 'connected')
        .sort((a, b) =>
            (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
        ),
);

// Get desired configs for selected cameras (for API calls)
export const selectSelectedCameraConfigs = createSelector(
    [selectSelectedCameras],
    (cameras): Record<string, CameraConfig> =>
        cameras
            .filter((cam) => cam.streamAvailable || cam.connectionStatus === 'connected')
            .reduce(
                (configs, camera) => ({
                    ...configs,
                    [camera.id]: camera.desiredConfig,
                }),
                {} as Record<string, CameraConfig>,
            ),
);



function unionNativeFpsCandidates(cameras: Camera[]): number[] {
    const raw: number[] = [];
    for (const cam of cameras) {
        raw.push(...uniqRepresentativeFpsFromFormats(cam.deviceInfo.availableFormats ?? []));
    }
    const out: number[] = [];
    for (const r of raw) {
        if (!out.some((e) => fpsValuesEquivalent(e, r))) {
            out.push(r);
        }
    }
    out.sort((a, b) => a - b);
    return out;
}

/** Native FPS presets common to **every** selected usable camera (`streamAvailable` or connected). */
export const selectIntersectingFpsOptions = createSelector(
    [selectSelectedCameras],
    (selected): number[] => {
        const eligible = selected
            .filter(
                (c) =>
                    (c.streamAvailable || c.connectionStatus === 'connected')
                    && ((c.deviceInfo.availableFormats?.length ?? 0) > 0),
            )
            .sort((a, b) => a.index - b.index);
        if (eligible.length === 0) {
            return [];
        }
        const candidates = unionNativeFpsCandidates(eligible);
        const options = candidates.filter((native) =>
            eligible.every((camera) =>
                formatsIncludeTargetFramerate(camera.deviceInfo.availableFormats, native),
            ),
        );
        return options;
    },
);

export const selectGroupDisplayedFramerate = createSelector(
    [selectSelectedCameras],
    (selected): number => {
        const eligible = selected
            .filter(
                (c) =>
                    (c.streamAvailable || c.connectionStatus === 'connected')
                    && ((c.deviceInfo.availableFormats?.length ?? 0) > 0),
            )
            .sort((a, b) => a.index - b.index);
        if (eligible.length === 0) {
            return -1;
        }
        const baseline = eligible[0].desiredConfig.framerate ?? -1;
        const allMatch = eligible.every((c) =>
            fpsValuesEquivalent(c.desiredConfig.framerate, baseline),
        );
        return allMatch ? baseline : -1;
    },
);

/**
 * Canonical FPS the Cameras bar is *visually* displaying — always an element of {@link selectIntersectingFpsOptions}
 * when there is a selection. Mirrors the dropdown's resolution rule in {@link CamerasSectionTopControls}
 * so tree rows can never disagree with the bar.
 *
 * ``null`` → no enforced target (no selection, or no shared intersect) → cameras render as plain Available.
 */
export const selectBarAppliedTargetFramerate = createSelector(
    [
        selectHasCameraSelection,
        selectIntersectingFpsOptions,
        selectGroupDisplayedFramerate,
    ],
    (hasSelection, fpsChoices, groupFpsDisplay): number | null => {
        if (!hasSelection || fpsChoices.length === 0) {
            return null;
        }
        // Same resolution path as the dropdown: prefer a value matching the unified group FPS,
        // otherwise default-in-intersect, otherwise first intersect FPS.
        const representativeMatchingGroup = fpsChoices.find((fps) =>
            fpsValuesEquivalent(fps, groupFpsDisplay),
        );
        const representativeWhenMixed =
            fpsChoices.find((fps) => fpsValuesEquivalent(fps, DEFAULT_UI_FRAMERATE))
            ?? fpsChoices[0];
        return representativeMatchingGroup ?? representativeWhenMixed ?? null;
    },
);

// Get actual configs for all cameras
export const selectActualCameraConfigs = createSelector(
    [selectCameras],
    (cameras): Record<string, CameraConfig> => {
        return cameras.reduce(
            (configs, camera) => ({
                ...configs,
                [camera.id]: camera.actualConfig,
            }),
            {} as Record<string, CameraConfig>
        );
    }
);

// ========== Mismatch Selectors ==========
export const selectCamerasWithConfigMismatch = createSelector(
    [selectCameras],
    (cameras) => cameras.filter(cam => cam.hasConfigMismatch)
);

export const selectHasAnyConfigMismatch = createSelector(
    [selectCamerasWithConfigMismatch],
    (camerasWithMismatch) => camerasWithMismatch.length > 0
);

export const selectCameraHasConfigMismatch = createSelector(
    [selectCameraById],
    (camera) => camera?.hasConfigMismatch ?? false
);

// Get config comparison for a specific camera
export const selectCameraConfigComparison = createSelector(
    [selectCameraById],
    (camera) => {
        if (!camera) return null;

        return {
            actual: camera.actualConfig,
            desired: camera.desiredConfig,
            hasMismatch: camera.hasConfigMismatch,
            differences: camera.hasConfigMismatch ?
                getConfigDifferences(camera.actualConfig, camera.desiredConfig) : []
        };
    }
);

// ========== Count Selectors ==========
export const selectCameraCount = createSelector(
    [selectCamerasDisplayedInUi],
    (cameras) => cameras.length,
);

export const selectHasConnectedCameras = createSelector(
    [selectConnectedCameras],
    (cameras) => cameras.length > 0
);

// ========== Helper Functions ==========
function getConfigDifferences(
    actual: CameraConfig,
    desired: CameraConfig
): Array<{ field: string; actual: any; desired: any }> {
    const differences: Array<{ field: string; actual: any; desired: any }> = [];

    // Compare each field
    if (actual.resolution.width !== desired.resolution.width) {
        differences.push({
            field: 'resolution.width',
            actual: actual.resolution.width,
            desired: desired.resolution.width
        });
    }
    if (actual.resolution.height !== desired.resolution.height) {
        differences.push({
            field: 'resolution.height',
            actual: actual.resolution.height,
            desired: desired.resolution.height
        });
    }
    if (actual.framerate !== desired.framerate) {
        differences.push({
            field: 'framerate',
            actual: actual.framerate,
            desired: desired.framerate
        });
    }
    if (actual.exposure_mode !== desired.exposure_mode) {
        differences.push({
            field: 'exposure_mode',
            actual: actual.exposure_mode,
            desired: desired.exposure_mode
        });
    }
    if (actual.exposure !== desired.exposure) {
        differences.push({
            field: 'exposure',
            actual: actual.exposure,
            desired: desired.exposure
        });
    }
    if (actual.rotation !== desired.rotation) {
        differences.push({
            field: 'rotation',
            actual: actual.rotation,
            desired: desired.rotation
        });
    }
    if (actual.pixel_format !== desired.pixel_format) {
        differences.push({
            field: 'pixel_format',
            actual: actual.pixel_format,
            desired: desired.pixel_format
        });
    }
    if (actual.capture_fourcc !== desired.capture_fourcc) {
        differences.push({
            field: 'capture_fourcc',
            actual: actual.capture_fourcc,
            desired: desired.capture_fourcc,
        });
    }
    if (actual.writer_fourcc !== desired.writer_fourcc) {
        differences.push({
            field: 'writer_fourcc',
            actual: actual.writer_fourcc,
            desired: desired.writer_fourcc,
        });
    }

    return differences;
}
