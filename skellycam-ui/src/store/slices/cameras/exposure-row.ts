// No imports: the node unit test loads this file directly.

/** A saved config with the old mode RECOMMEND loads as AUTO (camera-requests.md 1.8, G6 of ADR-JK79). */
export function normalizeExposureMode<T extends { exposure_mode?: string }>(config: T): T {
    return config.exposure_mode === 'RECOMMEND' ? { ...config, exposure_mode: 'AUTO' } : config;
}

interface HeldConfig {
    exposure_mode?: string;
    exposure: number;
    exposure_found_at_fps?: number | null;
}

interface WarningItem {
    kind: string;
    text?: string;
}

/** The status of one camera in the live state (CameraStatus.serialize() of the server, windows-capture.md 8.4). */
export interface ServerCameraStatus {
    state?: string | null;
    mode?: { fps_num: number; fps_den: number } | null;
    warnings?: WarningItem[];
    measured_fps?: number | null;
    exposure_search?: { state?: string } | null;
}

interface GroupState {
    configs: Record<string, HeldConfig & { framerate?: number }>;
    cameras?: Record<string, { status?: ServerCameraStatus }>;
}

/**
 * The exposure texts of a camera row (camera-requests.md 1.8): the chip (`E:-8`, `E:-8 auto`) and the i18n keys of
 * the row texts. The row never shows the measured numbers (H5, kept by ADR-6QFG).
 */
export function exposureRowText(
    config: HeldConfig,
    modeRate: number,
    state: string | undefined | null,
    warnings: WarningItem[],
    measuredFps: number | undefined | null,
): { chip: string | null; keys: string[] } {
    const kinds = warnings.map(item => item.kind);
    const keys: string[] = [];
    let chip: string | null = null;
    if (kinds.includes('no_manual_exposure')) {
        keys.push('noManualExposure');
    } else if (config.exposure_mode === 'AUTO' && config.exposure_found_at_fps == null) {
        keys.push('exposureAutoNoValue');
    } else {
        chip = `E:${config.exposure}${config.exposure_mode === 'AUTO' ? ' auto' : ''}`;
    }
    if (state === 'adjusting') keys.push('settingExposure');
    if (state === 'too_slow') keys.push(measuredFps != null && measuredFps > modeRate ? 'cameraDeliversMoreFrames' : 'cameraIsSlow');
    if (kinds.includes('add_light')) keys.push('addLight');
    if (kinds.includes('exposure_search_failed')) keys.push('exposureSearchFailed');
    if (kinds.includes('exposure_clamped')) keys.push('exposureClamped');  // a plain line of the row (1.8)
    return { chip, keys };
}

/**
 * Copy `exposure` and `exposure_found_at_fps` of each camera whose search is `done` into its desired config
 * (camera-requests.md 1.3b, 1.8) [B14]. Only a camera in AUTO on both sides: a desired MANUAL is an edit of the user.
 * Returns the same object when nothing changes.
 */
export function copyHeldValues<T extends HeldConfig>(
    desired: Record<string, T>,
    state: { camera_groups: Record<string, GroupState> },
): Record<string, T> {
    let result = desired;
    for (const group of Object.values(state.camera_groups)) {
        for (const [id, server] of Object.entries(group.configs)) {
            const wanted = result[id];
            const done = group.cameras?.[id]?.status?.exposure_search?.state === 'done';
            if (!wanted || !done || wanted.exposure_mode !== 'AUTO' || server.exposure_mode !== 'AUTO') continue;
            const foundAt = server.exposure_found_at_fps ?? null;
            if (wanted.exposure === server.exposure && (wanted.exposure_found_at_fps ?? null) === foundAt) continue;
            result = { ...result, [id]: { ...wanted, exposure: server.exposure, exposure_found_at_fps: foundAt } };
        }
    }
    return result;
}

/** The live status of one camera, or undefined when no group has it. */
export function serverStatusOf(groups: GroupState[], id: string): ServerCameraStatus | undefined {
    return groups.find(group => id in group.configs)?.cameras?.[id]?.status;
}

/** True while a camera of a group is in one of `states`. */
export function anyCameraIn(groups: GroupState[], states: string[]): boolean {
    return groups.some(group => Object.values(group.cameras ?? {}).some(camera => states.includes(camera.status?.state ?? '')));
}

/** True while a camera of a group runs its exposure search: no recording can start (camera-requests.md 1.3b) [G2]. */
export function anyAdjusting(groups: GroupState[]): boolean {
    return anyCameraIn(groups, ['adjusting']);
}

/** No search can start while a camera starts, waits or searches: the server answers 409 (camera-requests.md 1.5). */
export function searchBlocked(groups: GroupState[]): boolean {
    return anyCameraIn(groups, ['starting', 'waiting', 'adjusting']);
}

/** The mode rate of a camera on the server: the opened mode, else its server config, else `fallback`. */
export function serverModeRate(groups: GroupState[], id: string, fallback: number): number {
    const group = groups.find(item => id in item.configs);
    const mode = group?.cameras?.[id]?.status?.mode;
    if (mode && mode.fps_num > 0 && mode.fps_den > 0) return mode.fps_num / mode.fps_den;
    const rate = group?.configs[id]?.framerate;
    return rate !== undefined && rate > 0 ? rate : fallback;
}
