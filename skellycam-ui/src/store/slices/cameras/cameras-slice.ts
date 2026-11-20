// cameras-slice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
    CamerasState,
    CameraConfig, extractConfigSettings, areConfigsEqual, createDefaultCameraConfig,
} from './cameras-types';
import {
    detectCameras,
    camerasConnectOrUpdate,
    closeCameras,
    pauseUnpauseCameras,
} from './cameras-thunks';
import { serverStateReceived, serverDisconnected } from '../connection/connection-slice';
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

const initialState: CamerasState = {
    cameras: [],
    isPaused: false,
    isLoading: false,
    error: null,
};

export const cameraSlice = createSlice({
    name: 'cameras',
    initialState,
    reducers: {
        // ========== Selection ==========
        cameraSelectionToggled: (state, action: PayloadAction<string>) => {
            const camera = state.cameras.find(cam => cam.id === action.payload);
            if (camera && !camera.deviceInfo.virtual) {  // virtual cameras are not supported yet
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
                camera.selected = !camera.deviceInfo.virtual;
                camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, defaultConfig);
            }
        },


    },

    extraReducers: (builder) => {
        builder
            // ========== Detect Cameras ==========
            .addCase(detectCameras.pending, (state) => {
                state.isLoading = true;
                state.error = null;
            })
            .addCase(detectCameras.fulfilled, (state, action) => {
                state.isLoading = false;
                state.cameras = action.payload;
                persistAllCameraSettings(state);
            })
            .addCase(detectCameras.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.error.message || 'Failed to detect cameras';
            })

            // ========== Connect Cameras ==========
            .addCase(camerasConnectOrUpdate.pending, (state) => {
                state.isLoading = true;
                state.error = null;
            })
            .addCase(camerasConnectOrUpdate.fulfilled, (state, action) => {
                state.isLoading = false;
                const named = action.meta.arg;  // undefined: a full apply of the selected cameras
                state.cameras.forEach(camera => {
                    camera.inGroup = camera.id in action.payload.camera_configs;
                    if (!camera.inGroup) {
                        camera.connectionStatus = 'available';
                        camera.failure = undefined;
                    }
                });
                // Update both actual and desired configs from server response
                Object.entries(action.payload.camera_configs).forEach(
                    ([cameraId, config]) => {
                        const camera = state.cameras.find(cam => cam.id === cameraId);
                        if (camera && named && !(cameraId in named)) {
                            // not in a partial request ("Update Cameras"): keep its unsaved edits and its status
                            camera.actualConfig = config as CameraConfig;
                            camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
                        } else if (camera) {
                            camera.actualConfig = config as CameraConfig;
                            camera.desiredConfig = { ...config as CameraConfig };
                            camera.hasConfigMismatch = false;
                            const failure = action.payload.camera_failures?.[cameraId];
                            camera.connectionStatus = failure ? 'error' : 'connected';
                            camera.failure = failure ? `${failure.stage}: ${failure.reason}` : undefined;
                        }
                    }
                );
                persistAllCameraSettings(state);
            })
            .addCase(camerasConnectOrUpdate.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.error.message || 'Failed to connect to cameras';
            })


            // ========== Close Cameras ==========
            .addCase(closeCameras.fulfilled, (state) => {
                state.cameras.forEach(camera => {
                    camera.connectionStatus = 'available';
                    camera.inGroup = false;
                    camera.metrics = undefined;
                    camera.hasConfigMismatch = false;
                });
                state.isPaused = false;
            })

            // ========== Pause / Unpause Cameras ==========
            .addCase(pauseUnpauseCameras.fulfilled, (state, action) => {
                state.isPaused = action.payload;
            })

            // ========== Server state snapshot (authoritative) ==========
            // Reconcile observed connection + pause state from the pushed snapshot.
            .addCase(serverStateReceived, (state, action) => {
                const groups = Object.values(action.payload.state.camera_groups);
                const connectedIds = new Set<string>();
                const failures = new Map<string, string>();
                let anyPaused = false;
                for (const group of groups) {
                    if (group.paused) anyPaused = true;
                    // `group.alive` is false as soon as one camera process ended, so judge each camera
                    // by its own state: the other cameras of the group keep streaming.
                    for (const cameraId of Object.keys(group.configs)) {
                        const cam = group.cameras?.[cameraId];
                        const camState = cam?.status?.state;
                        if (camState === 'failed' || camState === 'dead' || camState === 'too_slow') {
                            const failure = cam?.status?.failure;
                            failures.set(cameraId, failure ? `${failure.stage}: ${failure.reason}` : camState);
                        } else if (group.alive || (cam?.alive && (camState === 'ready' || camState === 'recording'))) {
                            connectedIds.add(cameraId);
                        }
                    }
                }
                const groupIds = new Set(groups.flatMap(group => Object.keys(group.configs)));
                state.cameras.forEach(camera => {
                    camera.inGroup = groupIds.has(camera.id);
                    camera.connectionStatus = connectedIds.has(camera.id) ? 'connected'
                        : failures.has(camera.id) ? 'error' : 'available';
                    camera.failure = failures.get(camera.id);
                });
                state.isPaused = anyPaused;
            })

            // On websocket disconnect, reset to "not connected" so nothing goes stale.
            .addCase(serverDisconnected, (state) => {
                state.cameras.forEach(camera => {
                    camera.connectionStatus = 'available';
                    camera.inGroup = false;
                    camera.metrics = undefined;
                    camera.hasConfigMismatch = false;
                });
                state.isPaused = false;
            });
    },
});

export const {
    cameraSelectionToggled,
    cameraDesiredConfigUpdated,
    configCopiedToAll,
    savedSettingsCleared,
} = cameraSlice.actions;
