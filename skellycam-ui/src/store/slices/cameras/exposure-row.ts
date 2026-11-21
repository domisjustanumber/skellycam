// No imports: the node unit test loads this file directly.

/** A saved config with the old mode RECOMMEND loads as AUTO (camera-requests.md 1.8, G6 of ADR-JK79). */
export function normalizeExposureMode<T extends { exposure_mode?: string }>(config: T): T {
    return config.exposure_mode === 'RECOMMEND' ? { ...config, exposure_mode: 'AUTO' } : config;
}
