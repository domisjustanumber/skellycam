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
