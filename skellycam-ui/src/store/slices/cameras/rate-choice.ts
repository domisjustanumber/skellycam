// No imports: the node unit test loads this file directly.

/**
 * A saved config with the "auto" rate (-1 or 0) loads as 30: the UI never sends -1 or 0, and the server refuses a
 * group whose cameras request different rates (camera-requests.md 2.2, 2.8).
 */
export function normalizeFramerate<T extends { framerate?: number }>(config: T): T {
    return config.framerate !== undefined && config.framerate <= 0 ? { ...config, framerate: 30 } : config;
}

/** Within 0.5 fps of 60: a 60 fps mode (camera-requests.md 2.5). */
const near60 = (fps: number) => Math.abs(fps - 60) <= 0.5;

/** The states of a camera that opens, searches or checks (camera-requests.md 2.4). */
export const BUSY_STATES = ['starting', 'waiting', 'adjusting', 'checking'];

interface RateCamera {
    id: string;
    index: number;
    name: string;
    selected: boolean;
    desiredConfig: { framerate: number; resolution: { width: number; height: number } };
    deviceInfo: { supportedModes?: { width: number; height: number; framerates: number[] }[] };
}

interface LiveGroup {
    cameras?: Record<string, { status?: { state?: string | null; warnings?: { kind: string; text?: string }[] } }>;
}

/**
 * Whether the UI offers 60 fps: each selected camera has a rate within 0.5 fps of 60 at its size, and those rates are
 * equal (D17). Else the reasons, in the label form (camera-requests.md 2.5, 2.8).
 */
export function rateChoice(cameras: RateCamera[]): { can60: boolean; reasons: string[] } {
    const selected = cameras.filter(cam => cam.selected);
    const size = (cam: RateCamera) => `${cam.desiredConfig.resolution.width}x${cam.desiredConfig.resolution.height}`;
    const label = (cam: RateCamera) => `Camera ${cam.index} · ${cam.name}`;
    // The server takes the rate nearest to the request (7.5): 60 before 59.94 when a size has both
    const rates = selected.map(cam => cam.deviceInfo.supportedModes
        ?.find(mode => `${mode.width}x${mode.height}` === size(cam))?.framerates.filter(near60)
        .sort((a, b) => Math.abs(a - 60) - Math.abs(b - 60))[0]);
    const reasons = selected.flatMap((cam, i) => rates[i] === undefined ? [`${label(cam)} has no 60 fps mode at ${size(cam)}`] : []);
    if (reasons.length === 0 && selected.length > 0) {
        const top = Math.max(...(rates as number[]));
        selected.forEach((cam, i) => {
            if (Math.abs(rates[i]! - top) > 1e-4 * top) reasons.push(`${label(cam)} has ${rates[i]} fps, not ${top} fps, at ${size(cam)}`);
        });
    }
    return { can60: selected.length > 0 && reasons.length === 0, reasons };
}

/** The choice of the selector: 60 or 30, from the desired rate of the first selected camera, else of the first camera. */
export function chosenRate(cameras: { selected: boolean; desiredConfig: { framerate: number } }[]): number {
    const camera = cameras.find(cam => cam.selected) ?? cameras[0];
    return camera && near60(camera.desiredConfig.framerate) ? 60 : 30;
}

/**
 * The apply request of a pick: the applied config of each camera of the server's group with the new rate, and no
 * pending edit; "Update Cameras" adds the other cameras (camera-requests.md 2.8).
 */
export function rateRequestConfigs<C extends { framerate: number; use_this_camera: boolean }>(
    groupConfigs: Record<string, C>,
    rate: number,
): Record<string, C> {
    return Object.fromEntries(Object.entries(groupConfigs).map(([id, config]) => [id, { ...config, framerate: rate, use_this_camera: true }]));
}

/** A detection keeps one rate: each detected camera gets the choice of the list before it, else of the new list (2.8). */
export function withChosenRate<T extends { selected: boolean; desiredConfig: { framerate: number } }>(previous: T[], detected: T[]): T[] {
    const rate = chosenRate(previous.length > 0 ? previous : detected);
    return detected.map(cam => ({ ...cam, desiredConfig: { ...cam.desiredConfig, framerate: rate } }));
}

/** The text of the first `rate_fallback` item of the live state, or null (camera-requests.md 2.4, 2.8). */
export function rateFallbackText(groups: LiveGroup[]): string | null {
    for (const group of groups) {
        for (const camera of Object.values(group.cameras ?? {})) {
            const item = camera.status?.warnings?.find(warning => warning.kind === 'rate_fallback');
            if (item?.text) return item.text;
        }
    }
    return null;
}

/**
 * "Checking 60 fps…" (camera-requests.md 2.8): from a sent pick of 60 or a new fall back item, until no camera is busy
 * and no apply request of the UI runs.
 */
export function nextRateChecking(checking: boolean, busy: boolean, applying: boolean, newFallback: boolean): boolean {
    return newFallback || (checking && (busy || applying));
}
