// cameras-thunks.ts
import { createAsyncThunk } from '@reduxjs/toolkit';
import { RootState } from '../../types';
import { serverUrls } from '@/services';
import { backendFetch } from '@/services/electron-ipc/backend-fetch';
import {
    Camera,
    CameraConfig,
    DetectCamerasRequest,
    DetectCamerasResponse,
    CamerasConnectOrUpdateRequest,
    ConnectCamerasResponse,
    createDefaultCameraConfig,
    DEFAULT_UI_FRAMERATE,
} from './cameras-types';
import { recommendExposureQueued } from './cameras-slice';
import { selectSelectedCameraConfigs } from './cameras-selectors';
import {
    loadPersistedCameraSettings,
    savePersistedCameraSettings,
    PersistedCameraSettingsMap,
} from './camera-settings-storage';

export const detectCameras = createAsyncThunk<
    Camera[],
    DetectCamerasRequest | undefined,
    { state: RootState }
>(
    'cameras/detect',
    async (request = { filterVirtual: true }, { getState }) => {
        const state = getState();
        const existingCameras = state.cameras.cameras;
        const suppressListedVirtual = state.cameras.suppressListedVirtualCameras;

        const response = await backendFetch(serverUrls.endpoints.detectCameras, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filterVirtual: request?.filterVirtual ?? true,
                probeStreams: request?.probeStreams ?? true,
                skipListedVirtualResolutionInterrogation:
                    request?.skipListedVirtualResolutionInterrogation
                    ?? suppressListedVirtual,
            }),
        });

        if (!response.ok) {
            throw new Error(`Failed to detect cameras: ${response.statusText}`);
        }

        const data: DetectCamerasResponse = await response.json();

        // Load persisted settings from localStorage
        let persisted: PersistedCameraSettingsMap = {};
        try {
            persisted = loadPersistedCameraSettings();
        } catch {
            // Storage was corrupted and has been cleared — proceed with defaults
        }

        const detectedIds = new Set(data.cameras.map(c => c.camera_id));

        // Prune persisted entries for cameras that are no longer detected
        const prunedPersisted: PersistedCameraSettingsMap = {};
        for (const [id, settings] of Object.entries(persisted)) {
            if (detectedIds.has(id)) {
                prunedPersisted[id] = settings;
            }
        }
        savePersistedCameraSettings(prunedPersisted);

        return data.cameras.map((serverCamera): Camera => {
            const cameraId = serverCamera.camera_id;
            const existing = existingCameras.find(cam => cam.id === cameraId);
            const saved = prunedPersisted[cameraId];

            const streamAvailable = serverCamera.stream_available !== false;

            const defaultConfig = createDefaultCameraConfig(
                cameraId,
                serverCamera.index,
                serverCamera.name,
            );

            // Priority: existing in-memory state > persisted localStorage > defaults
            let desiredConfig: CameraConfig = existing?.desiredConfig
                ?? (saved ? { ...defaultConfig, ...saved.desiredConfig } : { ...defaultConfig });
            if (desiredConfig.framerate <= 0) {
                desiredConfig = { ...desiredConfig, framerate: DEFAULT_UI_FRAMERATE };
            }

            const matchesListed = serverCamera.matches_listed_virtual_name === true;
            const blockedListed = suppressListedVirtual && matchesListed;
            const selected: boolean =
                blockedListed ? false : (streamAvailable ? (existing?.selected ?? saved?.selected ?? true) : false);

            return {
                id: cameraId,
                name: serverCamera.name,
                index: serverCamera.index,
                actualConfig: existing?.actualConfig || defaultConfig,
                desiredConfig: { ...desiredConfig, use_this_camera: selected },
                hasConfigMismatch: existing?.hasConfigMismatch ?? false,
                connectionStatus: streamAvailable ? 'available' : 'unavailable',
                selected,
                streamAvailable,
                streamUnavailableReason: serverCamera.stream_unavailable_reason ?? null,
                matchesListedVirtualName: matchesListed,
                deviceInfo: {
                    uniqueId: serverCamera.unique_id ?? undefined,
                    matchesListedVirtualName: matchesListed,
                    supportsFocusManual: serverCamera.supports_focus_manual ?? false,
                    focusAutoSupported: serverCamera.focus_auto_supported ?? false,
                    focusMin: serverCamera.focus_min ?? null,
                    focusMax: serverCamera.focus_max ?? null,
                    focusDefault: serverCamera.focus_default ?? null,
                    availableFormats: serverCamera.available_formats,
                },
                metrics: existing?.metrics,
            };
        });
    }
);

export const camerasConnectOrUpdate = createAsyncThunk<
    ConnectCamerasResponse,
    void,
    { state: RootState }
>(
    'cameras/connect',
    async (_, { getState, dispatch }) => {
        const state = getState();
        const cameraConfigs = selectSelectedCameraConfigs(state);

        if (Object.keys(cameraConfigs).length === 0) {
            throw new Error(
                'No usable cameras selected for connection. If devices show as unavailable, they may be '
                + 'in use by another application — close it or click refresh to probe again.',
            );
        }

        const hasRecommend = Object.values(cameraConfigs).some((c) => c.exposure_mode === 'RECOMMEND');
        if (hasRecommend) {
            dispatch(recommendExposureQueued({ camera_ids: Object.keys(cameraConfigs) }));
        }

        const request: CamerasConnectOrUpdateRequest = { camera_configs: cameraConfigs };

        const timeoutMs = hasRecommend ? 120_000 : 20_000;
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
        let response: Response;
        try {
            response = await backendFetch(serverUrls.endpoints.camerasConnectOrUpdate, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request),
                signal: controller.signal,
            });
        } finally {
            window.clearTimeout(timeout);
        }

        if (!response.ok) {
            const errorBody = await response.json().catch(() => ({})) as {
                detail?:
                    | string
                    | Array<{ msg?: string } | string>
                    | { message?: string; user_guidance?: string; error_code?: string };
            };
            const d = errorBody.detail;
            let message: string;
            if (typeof d === 'string') {
                message = d;
            } else if (Array.isArray(d)) {
                message = d.map((x) => (typeof x === 'string' ? x : x?.msg ?? JSON.stringify(x))).join('; ');
            } else if (d && typeof d === 'object' && ('message' in d || 'user_guidance' in d)) {
                const parts: string[] = [];
                if (typeof d.message === 'string') {
                    parts.push(d.message);
                }
                if (
                    typeof d.user_guidance === 'string'
                    && (parts.length === 0 || !parts.some((p) => p.includes(d.user_guidance!)))
                ) {
                    parts.push(d.user_guidance);
                }
                message = parts.length > 0 ? parts.join('\n\n') : 'Failed to connect to cameras';
            } else {
                message = 'Failed to connect to cameras';
            }
            throw new Error(message);
        }

        return response.json() as Promise<ConnectCamerasResponse>;
    }
);


export const closeCameras = createAsyncThunk<void, void, { state: RootState }>(
    'cameras/close',
    async () => {
        const response = await backendFetch(serverUrls.endpoints.closeAll, {
            method: 'DELETE',
        });

        if (!response.ok) {
            throw new Error(`Failed to close cameras: ${response.statusText}`);
        }
    }
);

export const pauseUnpauseCameras = createAsyncThunk<void, void, { state: RootState }>(
    'cameras/pause',
    async () => {
        const response = await backendFetch(serverUrls.endpoints.pauseUnpauseCameras, {
            method: 'GET',
        });

        if (!response.ok) {
            throw new Error(`Failed to pause/unpause cameras: ${response.statusText}`);
        }
    }
);
