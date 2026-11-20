// No imports: the node unit test loads this file directly.

interface CameraForUpdate {
    id: string;
    selected: boolean;
    inGroup?: boolean;
    connectionStatus: string;
    failure?: string;
    deviceInfo: { virtual?: boolean };
}

/** The differences between the camera list and the server's camera group that "Update Cameras" sends. */
export function pendingCameraChanges(cameras: CameraForUpdate[]) {
    const failed = cameras.filter(cam => cam.selected && cam.connectionStatus === 'error');
    return {
        // too_slow with the same config is "no effect" on the server (spec 8.3): remove it, then add it again
        tooSlow: failed.filter(cam => cam.failure === 'too_slow').map(cam => cam.id),
        retry: failed.filter(cam => cam.failure !== 'too_slow').map(cam => cam.id),
        close: cameras.filter(cam => cam.inGroup && !cam.selected).map(cam => cam.id),
        add: cameras.filter(cam => cam.selected && !cam.deviceInfo.virtual && !cam.inGroup).map(cam => cam.id),
    };
}
