// No imports: the node unit test loads this file directly.

interface CameraForUpdate {
    id: string;
    selected: boolean;
    inGroup?: boolean;
    connectionStatus: string;  // 'error' only for a failed or dead camera: too_slow is connected (ruling 2 of ADR-F2KY)
    deviceInfo: { virtual?: boolean };
    index?: number;  // the current detection
    name?: string;
    actualConfig?: { camera_index: number; camera_name: string };  // what the server applied
}

export interface CameraChanges { retry: string[]; close: string[]; add: string[]; renumber: string[] }

/**
 * The differences between the camera list and the server's camera group that "Update Cameras" sends.
 * `groupIds`: each camera of the server's groups; one with no row (unplugged, then detected again) is closed.
 */
export function pendingCameraChanges(cameras: CameraForUpdate[], groupIds: string[] = []): CameraChanges {
    const rowIds = new Set(cameras.map(cam => cam.id));
    return {
        retry: cameras.filter(cam => cam.selected && cam.connectionStatus === 'error').map(cam => cam.id),
        close: [
            ...cameras.filter(cam => cam.inGroup && !cam.selected).map(cam => cam.id),
            ...groupIds.filter(id => !rowIds.has(id)),
        ],
        add: cameras.filter(cam => cam.selected && !cam.deviceInfo.virtual && !cam.inGroup).map(cam => cam.id),
        // A re-detection gave an open camera a new number or name: send it again, live with no reopen (camera-requests.md 8.1)
        renumber: cameras.filter(cam => cam.selected && cam.inGroup && cam.connectionStatus !== 'error' && cam.actualConfig
            && (cam.actualConfig.camera_index !== cam.index || cam.actualConfig.camera_name !== cam.name)).map(cam => cam.id),
    };
}

/** The camera_configs of the "Update Cameras" request: only the changed cameras; the server keeps the others as they are. */
export function updateRequestConfigs<C extends { use_this_camera: boolean }>(
    cameras: { id: string; desiredConfig: C }[],
    changes: CameraChanges,
    groupConfigs: Record<string, C>,
): Record<string, C> {
    const config = (id: string, use: boolean): [string, C] =>
        [id, { ...(cameras.find(cam => cam.id === id)?.desiredConfig ?? groupConfigs[id]), use_this_camera: use }];
    return Object.fromEntries([
        ...changes.close.map(id => config(id, false)),
        ...[...changes.retry, ...changes.add, ...changes.renumber].map(id => config(id, true)),
    ]);
}

/**
 * The cameras sent to open that the response leaves out. The server adds to a running group only a camera that was in
 * it before (camera_group.py apply); then the only way is the full sequence: close all, connect the selected.
 */
export function missingFromGroup(sent: Record<string, { use_this_camera: boolean }>, responseConfigs: Record<string, unknown>): string[] {
    return Object.entries(sent).filter(([id, config]) => config.use_this_camera && !(id in responseConfigs)).map(([id]) => id);
}

/**
 * The kind of an apply call: "Update Cameras", Connect with no group, or any other apply (settings, menu, grid,
 * welcome), which must stay a live change.
 */
export type ApplyKind = 'update-cameras' | 'connect' | 'settings';

/** Whether the thunk closes all cameras and connects the selected ones: only for a call meant to add cameras. */
export function closeAllAndConnect(kind: ApplyKind, sent: Record<string, { use_this_camera: boolean }>, responseConfigs: Record<string, unknown>): boolean {
    return kind !== 'settings' && missingFromGroup(sent, responseConfigs).length > 0;
}
