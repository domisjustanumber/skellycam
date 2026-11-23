// No imports: the node unit test loads this file directly.

/** Set camera_index and camera_name of each request config from the current detection (camera-requests.md 8.1). */
export function withDetectionNumbers<T extends { camera_index: number; camera_name: string }>(
    configs: Record<string, T>,
    cameras: { id: string; index: number; name: string }[],
): Record<string, T> {
    return Object.fromEntries(Object.entries(configs).map(([id, config]) => {
        const camera = cameras.find(cam => cam.id === id);
        // A camera that is not in the current detection keeps the number and the name it had (the spec does not say).
        return [id, camera ? { ...config, camera_index: camera.index, camera_name: camera.name } : config];
    }));
}

/**
 * The body of the apply request (POST /camera/group/apply): each config with the detection's number and name.
 * `retry`: the failed or dead cameras that the request opens again ("Update Cameras" only); the server restarts no
 * other failed camera (windows-capture.md 8.3, ADR-Z7F3).
 */
export function applyRequestBody<T extends { camera_index: number; camera_name: string }>(
    configs: Record<string, T>,
    cameras: { id: string; index: number; name: string }[],
    retry: string[] = [],
): { camera_configs: Record<string, T>; retry_camera_ids: string[] } {
    return { camera_configs: withDetectionNumbers(configs, cameras), retry_camera_ids: retry };
}
