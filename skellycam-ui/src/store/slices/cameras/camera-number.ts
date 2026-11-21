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

/** A config as the apply request sends it: the exposure mode can be RECOMMEND (see applyRequestBody). */
export type WireConfig<T> = Omit<T, 'exposure_mode'> & { exposure_mode?: string };

/** The body of the apply request (POST /camera/group/apply): each config with the detection's number and name. */
export function applyRequestBody<T extends { camera_index: number; camera_name: string; exposure_mode?: string }>(
    configs: Record<string, T>,
    cameras: { id: string; index: number; name: string }[],
): { camera_configs: Record<string, WireConfig<T>> } {
    // shortcut: today's server reads AUTO as the camera's own auto exposure, which the user forbids, and only RECOMMEND
    // runs the exposure search; so Auto goes on the wire as RECOMMEND. The server answers MANUAL with the found value,
    // and the panel then shows Manual at that value (the response becomes the desired config). Replace this with a plain
    // AUTO when the Auto step of the server (camera-requests.md 1.3) is merged.
    return { camera_configs: Object.fromEntries(Object.entries(withDetectionNumbers(configs, cameras)).map(([id, config]) =>
        [id, config.exposure_mode === 'AUTO' ? { ...config, exposure_mode: 'RECOMMEND' } : config])) };
}
