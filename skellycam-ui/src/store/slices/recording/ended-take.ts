// Only a relative import: the node unit test loads this file directly.
import { cameraLabel, labelText } from '../cameras/camera-labels.ts';

/** The fields of a camera group in the live state for a take that ended by itself with an error (recorder.md 8.4). */
export interface GroupTakeState {
    take_state?: string;  // 'none' | 'recording' | 'ended_with_error'; absent from a server that predates recorder.md 8.4
    ended_take_summary?: { take_error: string; camera_id: string | null; summary: unknown } | null;
}

export interface EndedTakeNotice { groupId: string; takeError: string; cameraId: string | null; summary: unknown }

/** The notice of a group that moves to "ended_with_error"; null while it stays there (camera-requests.md 8.4). */
export function endedTakeNotice(previous: Record<string, GroupTakeState> | null, state: Record<string, GroupTakeState>): EndedTakeNotice | null {
    for (const [groupId, group] of Object.entries(state)) {
        const ended = group.ended_take_summary;
        if (group.take_state === 'ended_with_error' && ended && previous?.[groupId]?.take_state !== 'ended_with_error') {
            return { groupId, takeError: ended.take_error, cameraId: ended.camera_id, summary: ended.summary };
        }
    }
    return null;
}

/** The error line of the notice with the camera label of 1.8; the label leads when the text does not name the camera. */
export function takeErrorText(notice: EndedTakeNotice, cameras: { id: string; index: number; name: string }[]): string {
    const text = labelText(notice.takeError, cameras);
    const camera = cameras.find(cam => cam.id === notice.cameraId);
    return camera && !text.includes(cameraLabel(camera)) ? `${cameraLabel(camera)}: ${text}` : text;
}

/** The changes of the recording slice for one app state; the slice assigns them. parseSummary checks the stop fields. */
export function recordingAfterAppState<C>(
    recording: { takeStates: Record<string, GroupTakeState>; endedTake: EndedTakeNotice | null },
    groups: Record<string, GroupTakeState & { recording_in_progress: boolean }>,
    parseSummary: (summary: unknown) => C | null,
): {
    isRecording: boolean; takeStates: Record<string, GroupTakeState>; endedTake?: EndedTakeNotice | null;
    recordingName?: null; startedAt?: null; duration?: number; completionData?: C | null;
} {
    const takeStates = Object.fromEntries(Object.entries(groups).map(([id, group]) => [id, { take_state: group.take_state }]));
    const isRecording = Object.values(groups).some(group => group.recording_in_progress);
    // A take that ended by itself with an error: Start again, the error and the summary at once, no stop request
    // (camera-requests.md 8.4). With no take_state from the server nothing else changes.
    const notice = endedTakeNotice(recording.takeStates, groups);
    if (notice) {
        return { isRecording: false, takeStates, endedTake: notice, recordingName: null, startedAt: null, duration: 0,
            completionData: parseSummary(notice.summary) };
    }
    const ended = recording.endedTake;
    // The line goes at a new take, at the stop request of 8.2, or when the group closes
    return ended && groups[ended.groupId]?.take_state !== 'ended_with_error'
        ? { isRecording, takeStates, endedTake: null } : { isRecording, takeStates };
}
