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
} from './cameras-thunks';
import { serverStateReceived, serverDisconnected } from '../connection/connection-slice';
import {
    savePersistedCameraSettings,
    clearPersistedCameraSettings,
    buildPersistedEntry,
    PersistedCameraSettingsMap,
} from './camera-settings-storage';
import { cameraStatesFromAppState, NOT_IN_GROUP, statusesAfterApply } from './camera-state';

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
        // Q495: pause freezes the display only; the cameras and a recording go on. Un-pause shows the current frame.
        displayPauseToggled(state) {
            state.isPaused = !state.isPaused;
        },
        // The camera list shows `error`; a new selection, Detect or Close makes it stale
        cameraErrorCleared(state) {
            state.error = null;
        },
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
                const { camera_configs: configs, camera_failures: failures, sentIds } = action.payload;
                const after = statusesAfterApply(state.cameras, configs, failures, sentIds);
                state.cameras.forEach(camera => {
                    const { status, sent } = after[camera.id];
                    Object.assign(camera, status);
                    const config = configs[camera.id] as CameraConfig | undefined;
                    if (!config) return;
                    camera.actualConfig = config;
                    if (sent) camera.desiredConfig = { ...config };  // a camera not in the request keeps its unsaved edits
                    camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
                });
                persistAllCameraSettings(state);
            })
            .addCase(camerasConnectOrUpdate.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.error.message || 'Failed to connect to cameras';
            })


            // ========== Close Cameras ==========
            .addCase(closeCameras.fulfilled, (state) => {
                state.cameras.forEach(camera => {
                    Object.assign(camera, NOT_IN_GROUP);
                    camera.metrics = undefined;
                    camera.hasConfigMismatch = false;
                });
                state.isPaused = false;
            })

            // ========== Server state snapshot (authoritative) ==========
            // Reconcile the observed connection state from the pushed snapshot.
            .addCase(serverStateReceived, (state, action) => {
                const live = cameraStatesFromAppState(Object.values(action.payload.state.camera_groups));
                state.cameras.forEach(camera => Object.assign(camera, live[camera.id] ?? NOT_IN_GROUP));
            })

            // On websocket disconnect, reset to "not connected" so nothing goes stale.
            .addCase(serverDisconnected, (state) => {
                state.cameras.forEach(camera => {
                    Object.assign(camera, NOT_IN_GROUP);
                    camera.metrics = undefined;
                    camera.hasConfigMismatch = false;
                });
                state.isPaused = false;
            });
    },
});

export const {
    displayPauseToggled,
    cameraErrorCleared,
    cameraSelectionToggled,
    cameraDesiredConfigUpdated,
    configCopiedToAll,
    savedSettingsCleared,
} = cameraSlice.actions;
