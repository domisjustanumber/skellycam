// cameras-slice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
    CamerasState,
    Camera,
    CameraConfig,
    cameraMatchesListedVirtualPattern,
    extractConfigSettings,
    areConfigsEqual,
    createDefaultCameraConfig,
    normalizeCaptureFourcc,
    pickBestFormatAtTargetFps,
} from './cameras-types';
import {
    detectCameras,
    camerasConnectOrUpdate,
    closeCameras,
    pauseUnpauseCameras,
} from './cameras-thunks';
import {
    savePersistedCameraSettings,
    clearPersistedCameraSettings,
    buildPersistedEntry,
    PersistedCameraSettingsMap,
} from './camera-settings-storage';

// Persist all current camera desired configs + selection to localStorage
function persistAllCameraSettings(state: CamerasState): void {
    const settingsMap: PersistedCameraSettingsMap = {};
    for (const camera of state.cameras) {
        settingsMap[camera.id] = buildPersistedEntry(camera.desiredConfig, camera.selected);
    }
    savePersistedCameraSettings(settingsMap);
}

function refreshCombinedLoading(state: CamerasState): void {
    state.isLoading = state.isDetectingCameras || state.isApplyingCameraConnection;
}

const initialState: CamerasState = {
    cameras: [],
    isPaused: false,
    isLoading: false,
    isDetectingCameras: false,
    isApplyingCameraConnection: false,
    suppressListedVirtualCameras: true,
    hardwareCameraEnumerationChanged: false,
    error: null,
};

export const cameraSlice = createSlice({
    name: 'cameras',
    initialState,
    reducers: {
        // ========== Selection ==========
        cameraSelectionToggled: (state, action: PayloadAction<string>) => {
            const camera = state.cameras.find(cam => cam.id === action.payload);
            if (camera) {
                const turningOn = !camera.selected;
                if (
                    turningOn
                    && !camera.streamAvailable
                    && camera.connectionStatus !== 'connected'
                ) {
                    return;
                }
                if (turningOn && state.suppressListedVirtualCameras && cameraMatchesListedVirtualPattern(camera)) {
                    return;
                }
                camera.selected = !camera.selected;
                camera.desiredConfig.use_this_camera = camera.selected;
            }
            persistAllCameraSettings(state);
        },

        // ========== Configuration ==========
        // User updates desired config
        cameraDesiredConfigUpdated: (
            state,
            action: PayloadAction<{
                cameraId: string;
                config: Partial<CameraConfig>
            }>
        ) => {
            const camera = state.cameras.find(
                cam => cam.id === action.payload.cameraId
            );
            if (camera) {
                camera.desiredConfig = { ...camera.desiredConfig, ...action.payload.config };
                // Check if there's now a mismatch
                camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
            }
            persistAllCameraSettings(state);
        },


        configCopiedToAll: (state, action: PayloadAction<string>) => {
            const sourceCamera = state.cameras.find(cam => cam.id === action.payload);
            if (!sourceCamera) return;

            // Extract copyable settings (exclude identity fields)
            const settings = extractConfigSettings(sourceCamera.desiredConfig);

            state.cameras.forEach(camera => {
                if (camera.id !== action.payload) {
                    if (
                        state.suppressListedVirtualCameras
                        && cameraMatchesListedVirtualPattern(camera)
                    ) {
                        return;
                    }
                    if (
                        !camera.streamAvailable
                        && camera.connectionStatus !== 'connected'
                    ) {
                        return;
                    }
                    camera.desiredConfig = {
                        ...camera.desiredConfig,
                        ...settings
                    };
                    camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
                }
            });
            persistAllCameraSettings(state);
        },

        savedSettingsCleared: (state) => {
            clearPersistedCameraSettings();
            for (const camera of state.cameras) {
                const defaultConfig = createDefaultCameraConfig(
                    camera.id,
                    camera.index,
                    camera.name,
                );
                camera.desiredConfig = defaultConfig;
                const selectable = !(state.suppressListedVirtualCameras && cameraMatchesListedVirtualPattern(camera));
                camera.selected = selectable;
                camera.desiredConfig.use_this_camera = selectable;
                camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, defaultConfig);
            }
        },

        suppressListedVirtualCamerasSet: (state, action: PayloadAction<boolean>) => {
            state.suppressListedVirtualCameras = action.payload;
            if (action.payload) {
                state.cameras.forEach(camera => {
                    if (cameraMatchesListedVirtualPattern(camera)) {
                        camera.selected = false;
                        camera.desiredConfig = {
                            ...camera.desiredConfig,
                            use_this_camera: false,
                        };
                    }
                });
                persistAllCameraSettings(state);
            }
        },

        hardwareCameraEnumerationChanged: (state) => {
            state.hardwareCameraEnumerationChanged = true;
        },

        dismissHardwareCameraEnumerationHint: (state) => {
            state.hardwareCameraEnumerationChanged = false;
        },

        camerasGroupFramerateSet: (state, action: PayloadAction<number>) => {
            const fps = action.payload;
            state.cameras.forEach(camera => {
                if (!camera.selected) return;
                const usable = camera.streamAvailable || camera.connectionStatus === 'connected';
                if (!usable) return;
                if (state.suppressListedVirtualCameras && cameraMatchesListedVirtualPattern(camera)) {
                    return;
                }
                const best = pickBestFormatAtTargetFps(camera.deviceInfo.availableFormats, fps);
                if (best) {
                    const applied = best.fps;
                    camera.desiredConfig = {
                        ...camera.desiredConfig,
                        framerate: applied,
                        resolution: { width: best.width, height: best.height },
                        capture_fourcc: normalizeCaptureFourcc(best.fourcc_str),
                    };
                }
                else {
                    camera.desiredConfig = { ...camera.desiredConfig, framerate: fps };
                }
                camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
            });
            persistAllCameraSettings(state);
        },

        recommendExposureQueued: (state, action: PayloadAction<{ camera_ids: readonly string[] }>) => {
            for (const cid of action.payload.camera_ids) {
                const cam = state.cameras.find(c => c.id === cid);
                if (!cam || cam.desiredConfig.exposure_mode !== 'RECOMMEND') continue;
                cam.desiredConfig = {
                    ...cam.desiredConfig,
                    exposure_mode: 'MANUAL',
                    exposure: -7,
                };
            }
            persistAllCameraSettings(state);
        },
    },

    extraReducers: (builder) => {
        builder
            // ========== Detect Cameras ==========
            .addCase(detectCameras.pending, (state) => {
                state.isDetectingCameras = true;
                refreshCombinedLoading(state);
                state.error = null;
            })
            .addCase(detectCameras.fulfilled, (state, action) => {
                state.isDetectingCameras = false;
                refreshCombinedLoading(state);
                state.cameras = action.payload;
                state.hardwareCameraEnumerationChanged = false;
                persistAllCameraSettings(state);
            })
            .addCase(detectCameras.rejected, (state, action) => {
                state.isDetectingCameras = false;
                refreshCombinedLoading(state);
                state.error = action.error.message || 'Failed to detect cameras';
            })

            // ========== Connect Cameras ==========
            .addCase(camerasConnectOrUpdate.pending, (state) => {
                state.isApplyingCameraConnection = true;
                refreshCombinedLoading(state);
                state.error = null;
            })
            .addCase(camerasConnectOrUpdate.fulfilled, (state, action) => {
                state.isApplyingCameraConnection = false;
                refreshCombinedLoading(state);
                // Update both actual and desired configs from server response
                Object.entries(action.payload.camera_configs).forEach(
                    ([cameraId, config]) => {
                        const camera = state.cameras.find(cam => cam.id === cameraId);
                        if (camera) {
                            camera.actualConfig = config as CameraConfig;
                            camera.desiredConfig = { ...config as CameraConfig };
                            camera.hasConfigMismatch = false;
                            camera.connectionStatus = 'connected';
                        }
                    }
                );
                persistAllCameraSettings(state);
            })
            .addCase(camerasConnectOrUpdate.rejected, (state, action) => {
                state.isApplyingCameraConnection = false;
                refreshCombinedLoading(state);
                state.error = action.error.message || 'Failed to connect to cameras';
            })


            // ========== Close Cameras ==========
            .addCase(closeCameras.fulfilled, (state) => {
                state.cameras.forEach(camera => {
                    camera.connectionStatus = camera.streamAvailable ? 'available' : 'unavailable';
                    camera.metrics = undefined;
                    camera.hasConfigMismatch = false;
                });
                state.isPaused = false;
            })

            // ========== Pause / Unpause Cameras ==========
            .addCase(pauseUnpauseCameras.fulfilled, (state) => {
                state.isPaused = !state.isPaused;
            });
    },
});

export const {
    cameraSelectionToggled,
    cameraDesiredConfigUpdated,
    configCopiedToAll,
    savedSettingsCleared,
    suppressListedVirtualCamerasSet,
    hardwareCameraEnumerationChanged,
    dismissHardwareCameraEnumerationHint,
    camerasGroupFramerateSet,
    recommendExposureQueued,
} = cameraSlice.actions;
