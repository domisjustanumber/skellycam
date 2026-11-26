// The values of the text messages for the preview (specs/preview-4b.md 5.4, 5.5): pure functions, so that the Node
// unit tests load them. The provider calls them and stores the results.
import type {CameraStateName} from '../../../player/index.ts';
import {cameraLabel} from '../../../store/slices/cameras/camera-labels.ts';

export interface ListedCamera {
    id: string;
    index: number;
    name: string;
}

export interface CameraOverlay {
    label: string | null;
    cameraState: CameraStateName | null;
}

export interface AppStateValues {
    overlays: Record<string, CameraOverlay>;
    gridCameraIds: string[];
    connectedCameraIds: string[];
}

interface GroupState {
    cameras?: Record<string, {status?: {state?: unknown; replaced_count?: number} | null} | null>;
    configs?: Record<string, {camera_index?: number; camera_name?: string} | null>;
}

export interface AppStateLike {
    state?: {camera_groups?: Record<string, GroupState | null>};
}

export interface FramerateUpdate {
    message_type: 'framerate_update';
    camera_group_id: string;
    cameras: Record<string, {
        delivered_framerate: {mean_frames_per_second: number} | null;
        not_shown_count: number;
        ring_skipped_count: number;
        oversize_count: number;
    }>;
}

const STATES: ReadonlySet<string> = new Set(['starting', 'waiting', 'failed', 'checking', 'too_slow', 'ready', 'recording', 'dead']);
const STREAMING: ReadonlySet<string> = new Set(['checking', 'too_slow', 'ready', 'recording']);   // [Q7, Q10]

/** The camera state of a status: one of the eight states, else null [A4]. */
export function cameraStateOf(status: {state?: unknown} | null | undefined): CameraStateName | null {
    const state = status?.state;
    return typeof state === 'string' && STATES.has(state) ? (state as CameraStateName) : null;
}

/** Each camera of `cameras` of each group, with no filter on `alive` (4.5) [Q7]: its overlay values, the grid in the
 * order of the camera list (list number, then id) [Q5], and the cameras that stream. */
export function appStateValues(message: AppStateLike, cameraList: ListedCamera[]): AppStateValues {
    const overlays: Record<string, CameraOverlay> = {};
    const order: [number, string][] = [];
    const states: Record<string, CameraStateName | null> = {};
    for (const group of Object.values(message.state?.camera_groups ?? {})) {
        for (const [id, camera] of Object.entries(group?.cameras ?? {})) {
            const listed = cameraList.find(c => c.id === id);
            const config = group?.configs?.[id];
            const index = listed?.index ?? config?.camera_index;
            const name = listed?.name ?? config?.camera_name;
            const cameraState = cameraStateOf(camera?.status);
            overlays[id] = {label: index === undefined || name === undefined ? null : cameraLabel({id, index, name}), cameraState};
            states[id] = cameraState;
            order.push([index ?? Number.MAX_SAFE_INTEGER, id]);
        }
    }
    order.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
    const gridCameraIds = order.map(([, id]) => id);
    return {overlays, gridCameraIds, connectedCameraIds: gridCameraIds.filter(id => STREAMING.has(states[id] ?? ''))};
}

/** `replaced_count` of the status of each camera of each group (5.8) [A2]. */
export function replacedCounts(message: AppStateLike): Record<string, number> {
    const out: Record<string, number> = {};
    for (const group of Object.values(message.state?.camera_groups ?? {})) {
        for (const [id, camera] of Object.entries(group?.cameras ?? {})) {
            const n = camera?.status?.replaced_count;
            if (typeof n === 'number') out[id] = n;
        }
    }
    return out;
}

/** The new shape of `framerate_update` [4a 6.2]: `message_type` and an object `cameras`. */
export function isFramerateUpdate(data: unknown): data is FramerateUpdate {
    const d = data as {message_type?: unknown; cameras?: unknown} | null;
    return !!d && typeof d === 'object' && d.message_type === 'framerate_update'
        && !!d.cameras && typeof d.cameras === 'object' && !Array.isArray(d.cameras);
}

/** The rate text of each camera: the Captured rate to 1 decimal and " fps"; null when it is null [A3]. */
export function rateTexts(message: FramerateUpdate): Record<string, string | null> {
    const out: Record<string, string | null> = {};
    for (const [id, camera] of Object.entries(message.cameras)) {
        const fps = camera?.delivered_framerate?.mean_frames_per_second;
        out[id] = typeof fps === 'number' ? `${fps.toFixed(1)} fps` : null;
    }
    return out;
}
