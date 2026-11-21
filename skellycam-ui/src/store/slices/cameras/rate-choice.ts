// No imports: the node unit test loads this file directly.

/**
 * A saved config with the "auto" rate (-1 or 0) loads as 30: the UI never sends -1 or 0, and the server refuses a
 * group whose cameras request different rates (camera-requests.md 2.2, 2.8).
 */
export function normalizeFramerate<T extends { framerate?: number }>(config: T): T {
    return config.framerate !== undefined && config.framerate <= 0 ? { ...config, framerate: 30 } : config;
}
