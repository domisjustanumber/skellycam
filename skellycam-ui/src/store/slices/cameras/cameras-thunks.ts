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
} from './cameras-types';
import { selectSelectedCameraConfigs } from './cameras-selectors';
import { applyRequestBody } from './camera-number';
import { ApplyKind, closeAllAndConnect } from './camera-updates';
import { cameraStatesFromAppState, NOT_IN_GROUP } from './camera-state';
import { normalizeExposureMode } from './exposure-row';
import { normalizeFramerate } from './rate-choice';
import { errorDetail } from '../error-detail';
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

        const response = await backendFetch(serverUrls.endpoints.detectCameras, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
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
        // The live state of each camera comes from the last app state: a detection does not reset it (the server sends
        // the app state only when it changes).
        const live = cameraStatesFromAppState(getState().connection.cameraGroups);

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

            const defaultConfig = createDefaultCameraConfig(
                cameraId,
                serverCamera.index,
                serverCamera.name,
            );

            // Priority: existing in-memory state > persisted localStorage > defaults
            const desiredConfig: CameraConfig = existing?.desiredConfig
                ?? (saved ? { ...defaultConfig, ...normalizeFramerate(normalizeExposureMode(saved.desiredConfig)) } : { ...defaultConfig });

            // A virtual camera (e.g. NDI) is never ticked, also over a stored selection: the server refuses it
            const selected: boolean = !serverCamera.virtual && (existing?.selected ?? saved?.selected ?? true);

            return {
                id: cameraId,
                name: serverCamera.name,
                index: serverCamera.index,
                actualConfig: existing?.actualConfig || defaultConfig,
                desiredConfig,
                hasConfigMismatch: existing?.hasConfigMismatch ?? false,
                ...(live[cameraId] ?? NOT_IN_GROUP),
                selected,
                deviceInfo: {
                    virtual: serverCamera.virtual,
                    usbLink: serverCamera.usb_link,
                    vendorId: serverCamera.vendor_id,
                    productId: serverCamera.product_id,
                },
                metrics: existing?.metrics,
            };
        });
    }
);

async function applyConfigs(configs: Record<string, CameraConfig>, cameras: Camera[]): Promise<ConnectCamerasResponse> {
    // A stored config can hold the number of an earlier detection: the request never sends it (camera-requests.md 8.1)
    const request: CamerasConnectOrUpdateRequest = applyRequestBody(configs, cameras);
    const response = await backendFetch(serverUrls.endpoints.camerasConnectOrUpdate, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    if (!response.ok) {
        throw new Error(errorDetail(await response.json().catch(() => null), response.statusText));
    }
    return response.json() as Promise<ConnectCamerasResponse>;
}

/** The response, and the ids of the cameras that the last request sent: only their status and desired config change. */
export type ConnectResult = ConnectCamerasResponse & { sentIds: string[] };

export const camerasConnectOrUpdate = createAsyncThunk<
    ConnectResult,
    // configs: only these cameras ("Update Cameras"), else each selected camera; kind: see closeAllAndConnect
    { configs?: Record<string, CameraConfig>; kind?: ApplyKind } | undefined,
    { state: RootState }
>(
    'cameras/connect',
    async ({ configs: onlyConfigs, kind = 'settings' } = {}, { getState, dispatch }) => {
        const configs = onlyConfigs ?? selectSelectedCameraConfigs(getState());
        if (Object.keys(configs).length === 0) {
            throw new Error('No cameras selected for connection');
        }
        const response = await applyConfigs(configs, getState().cameras.cameras);
        if (!closeAllAndConnect(kind, configs, response.camera_configs)) {
            return { ...response, sentIds: Object.keys(configs) };
        }
        // The server left out a camera to open (a new camera in a running or empty group): close all, connect the selected.
        // shortcut: today's server cannot add a new camera to a running group, so this reopens every camera; drop it when
        // the server can add one.
        await dispatch(closeCameras()).unwrap();
        const all = selectSelectedCameraConfigs(getState());
        return { ...(await applyConfigs(all, getState().cameras.cameras)), sentIds: Object.keys(all) };
    }
);


/** The response of POST /camera/group/exposure/auto (camera-requests.md 1.5). */
export interface ExposureSearchResponse {
    camera_configs: Record<string, CameraConfig>;
    results: Record<string, { state: string }>;
    warnings: { kind: string; camera_ids: string[]; text: string }[];
}

/** The button "Auto-set exposure (all cameras)" (no ids) and "Search again" (one id). The live state shows the rest. */
export const searchExposure = createAsyncThunk<ExposureSearchResponse, string[] | undefined, { state: RootState }>(
    'cameras/searchExposure',
    async (cameraIds) => {
        const response = await backendFetch(serverUrls.endpoints.exposureAuto, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cameraIds ? { camera_ids: cameraIds } : null),
        });
        if (!response.ok) {
            throw new Error(errorDetail(await response.json().catch(() => null), response.statusText));
        }
        return response.json() as Promise<ExposureSearchResponse>;
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
