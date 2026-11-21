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
    searchExposure,
} from './cameras-thunks';
import { copyHeldValues } from './exposure-row';
import { serverStateReceived, serverDisconnected } from '../connection/connection-slice';
import {
    savePersistedCameraSettings,
    clearPersistedCameraSettings,
    buildPersistedEntry,
    PersistedCameraSettingsMap,
} from './camera-settings-storage';
import { cameraStatesFromAppState, NOT_IN_GROUP, statusesAfterApply } from './camera-state';
import {
    BUSY_STATES, chosenRate, nextRateChecking, rateCheckingAtResponse, rateChoice, rateFallbackText, replacesDesired,
    withChosenRate,
} from './rate-choice';
import { labelText } from './camera-labels';

/** One rate for each camera (camera-requests.md 2.2, 2.8): the desired config of each camera gets it. */
const anyBusy = (state: CamerasState) => state.cameras.some(camera => BUSY_STATES.includes(camera.state ?? ''));

function setRate(state: CamerasState, rate: number): void {
    state.cameras.forEach(camera => {
        camera.desiredConfig.framerate = rate;
        camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
    });
}

/** Copy the held value of each camera whose search is done into its desired config (camera-requests.md 1.3a, 1.8). */
function adoptHeldValues(state: CamerasState, groups: Parameters<typeof copyHeldValues>[1]): void {
    const desired = Object.fromEntries(state.cameras.map(camera => [camera.id, camera.desiredConfig]));
    const copied = copyHeldValues(desired, groups);
    if (copied === desired) return;
    state.cameras.forEach(camera => { camera.desiredConfig = copied[camera.id]; });
    persistAllCameraSettings(state);
}

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
    rateNote: null,
    rateFallbackSeen: null,
    rateChecking: false,
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
                const choice = rateChoice(state.cameras);
                if (camera.selected && chosenRate(state.cameras) === 60 && !choice.can60) {  // camera-requests.md 2.5
                    setRate(state, 30);
                    state.rateNote = choice.reasons.join(' ');
                }
            }
            persistAllCameraSettings(state);
        },

        // ========== Frame rate (camera-requests.md 2.8) ==========
        // A pick of the one rate selector; the panel sends it at once while cameras stream (`check`: a sent pick of 60)
        frameRateChosen: (state, action: PayloadAction<{ rate: number; check: boolean }>) => {
            setRate(state, action.payload.rate);
            state.rateNote = null;
            state.rateChecking = action.payload.check;
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
                state.cameras = withChosenRate(state.cameras, action.payload);  // one rate also for a new camera (2.8)
                state.rateNote = null;  // a detection clears the note under the rate selector (2.4)
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
                const kind = action.meta.arg?.kind ?? 'settings';
                const autoSent = sentIds.some(id => (configs[id] as CameraConfig | undefined)?.exposure_mode === 'AUTO');
                state.rateChecking = rateCheckingAtResponse(state.rateChecking, autoSent, anyBusy(state));
                const after = statusesAfterApply(state.cameras, configs, failures, sentIds);
                state.cameras.forEach(camera => {
                    const { status, sent } = after[camera.id];
                    Object.assign(camera, status);
                    const config = configs[camera.id] as CameraConfig | undefined;
                    if (!config) return;
                    camera.actualConfig = config;
                    // a camera not in the request, and each camera of a pick, keeps its unsaved edits (camera-requests.md 2.8)
                    if (replacesDesired(kind, sent)) camera.desiredConfig = { ...config };
                    camera.hasConfigMismatch = !areConfigsEqual(camera.actualConfig, camera.desiredConfig);
                });
                persistAllCameraSettings(state);
            })
            .addCase(camerasConnectOrUpdate.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.error.message || 'Failed to connect to cameras';
                state.rateChecking = false;
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
                adoptHeldValues(state, action.payload.state);  // a search at an open: no response carries it [B14]
                // 2.4: a new fall back to 30 fps. An item seen before (a state from before a pick or a detection) is old.
                const fallback = rateFallbackText(Object.values(action.payload.state.camera_groups));
                const newFallback = fallback !== null && fallback !== state.rateFallbackSeen;
                state.rateChecking = nextRateChecking(state.rateChecking, anyBusy(state), state.isLoading, newFallback);
                if (fallback && newFallback) {
                    setRate(state, 30);
                    state.rateNote = labelText(fallback, state.cameras);
                    persistAllCameraSettings(state);
                }
                state.rateFallbackSeen = fallback;
            })

            .addCase(searchExposure.rejected, (state, action) => {
                state.error = action.error.message || 'The exposure search failed';
            })

            // ========== Exposure search on request (camera-requests.md 1.5) ==========
            // The server set each searched camera to Auto; its response carries the held values [A6].
            .addCase(searchExposure.fulfilled, (state, action) => {
                const { camera_configs: configs, results } = action.payload;
                state.cameras.forEach(camera => {
                    if (results[camera.id]?.state === 'done') camera.desiredConfig = { ...camera.desiredConfig, exposure_mode: 'AUTO' };
                });
                const cameras = Object.fromEntries(Object.entries(results).map(([id, result]) => [id, { status: { exposure_search: result } }]));
                adoptHeldValues(state, { camera_groups: { response: { configs, cameras } } });
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
    frameRateChosen,
    cameraDesiredConfigUpdated,
    configCopiedToAll,
    savedSettingsCleared,
} = cameraSlice.actions;
