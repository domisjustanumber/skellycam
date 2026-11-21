// No imports: the node unit test loads this file directly.

/** The states in which a camera streams: it keeps its tile and counts in "N Streaming" (ruling 2 of ADR-F2KY, Q10 of ADR-VYS7). */
const CONNECTED_STATES = ['checking', 'adjusting', 'too_slow', 'ready', 'recording'];
const FAILED_STATES = ['failed', 'dead'];

export interface LiveCameraStatus {
    inGroup: boolean;
    connectionStatus: 'available' | 'connected' | 'error';
    failure: string | undefined;  // "stage: reason" of a failed or dead camera
    state: string | undefined;    // the server state of the camera
}

export const NOT_IN_GROUP: LiveCameraStatus = { inGroup: false, connectionStatus: 'available', failure: undefined, state: undefined };

interface GroupForStatus {
    configs: Record<string, unknown>;
    cameras?: Record<string, { status?: { state?: string | null; failure?: { stage: string; reason: string } | null } }>;
}

/** The live status of each camera of the server's camera groups, judged by its own state: an unknown state is not connected. */
export function cameraStatesFromAppState(groups: GroupForStatus[]): Record<string, LiveCameraStatus> {
    const result: Record<string, LiveCameraStatus> = {};
    for (const group of groups) {
        for (const cameraId of Object.keys(group.configs)) {
            const status = group.cameras?.[cameraId]?.status;
            const state = status?.state ?? undefined;
            const failed = state !== undefined && FAILED_STATES.includes(state);
            result[cameraId] = {
                inGroup: true,
                connectionStatus: failed ? 'error' : state !== undefined && CONNECTED_STATES.includes(state) ? 'connected' : 'available',
                failure: failed ? (status?.failure ? `${status.failure.stage}: ${status.failure.reason}` : state) : undefined,
                state,
            };
        }
    }
    return result;
}

const RESTARTING: LiveCameraStatus = { inGroup: true, connectionStatus: 'available', failure: undefined, state: undefined };

/**
 * The live status of each camera after an apply response, and whether the request sent it (only a sent camera takes
 * the response as its desired config). A response never claims that a camera streams: a new or retried camera waits
 * for the app state; a sent open camera keeps its status (a live change); a failure replaces the state.
 */
export function statusesAfterApply(
    cameras: { id: string; inGroup?: boolean; connectionStatus: LiveCameraStatus['connectionStatus']; failure?: string; state?: string }[],
    responseConfigs: Record<string, unknown>,
    failures: Record<string, { stage: string; reason: string }> | undefined,
    sentIds: string[],
): Record<string, { status: LiveCameraStatus; sent: boolean }> {
    return Object.fromEntries(cameras.map(camera => {
        const sent = sentIds.includes(camera.id);
        const failure = failures?.[camera.id];
        const kept: LiveCameraStatus = { inGroup: true, connectionStatus: camera.connectionStatus, failure: camera.failure, state: camera.state };
        const status: LiveCameraStatus = !(camera.id in responseConfigs) ? NOT_IN_GROUP
            : !sent ? kept
            : failure ? { inGroup: true, connectionStatus: 'error', failure: `${failure.stage}: ${failure.reason}`, state: 'failed' }
            : camera.inGroup && camera.connectionStatus !== 'error' ? kept
            : RESTARTING;
        return [camera.id, { status, sent }];
    }));
}
