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

const BUSY_STATES = ['starting', 'waiting', 'adjusting', 'checking'];

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

/** The apply request of a pick: each camera of the server's group with the new rate; "Update Cameras" adds the others. */
export function rateRequestConfigs<C extends { framerate: number; use_this_camera: boolean }>(
    cameras: { id: string; desiredConfig: C }[],
    groupConfigs: Record<string, C>,
    rate: number,
): Record<string, C> {
    return Object.fromEntries(Object.keys(groupConfigs).map(id =>
        [id, { ...(cameras.find(cam => cam.id === id)?.desiredConfig ?? groupConfigs[id]), framerate: rate, use_this_camera: true }]));
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

/** "Checking 60 fps…": a camera starts, waits, searches or checks after a pick of 60 or during a fall back (2.4, 2.8). */
export function checkingRate(groups: LiveGroup[], choice: number): boolean {
    const busy = groups.some(group => Object.values(group.cameras ?? {}).some(camera => BUSY_STATES.includes(camera.status?.state ?? '')));
    return busy && (choice === 60 || rateFallbackText(groups) !== null);
}
