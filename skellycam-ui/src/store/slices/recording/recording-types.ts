import { z } from 'zod';
import type { EndedTakeNotice, GroupTakeState } from './ended-take';

const StatsSummarySchema = z.object({
    median: z.number(),
    mean: z.number(),
    std: z.number(),
    min: z.number(),
    max: z.number(),
});

export type StatsSummary = z.infer<typeof StatsSummarySchema>;

export const StopRecordingResponseSchema = z.object({
    recording_name: z.string(),
    recording_path: z.string(),
    number_of_cameras: z.number(),
    number_of_frames: z.number(),
    total_duration_sec: z.number(),
    mean_framerate: z.number(),
    mean_inter_camera_sync_ms: z.number(),
    framerate_stats: StatsSummarySchema,
    frame_duration_stats: StatsSummarySchema,
    inter_camera_grab_range_ms_stats: StatsSummarySchema,
});

export type RecordingCompletionData = z.infer<typeof StopRecordingResponseSchema>;

export const RecordingInfoSchema = z.object({
    isRecording: z.boolean(),
    recordingDirectory: z.string(),
    recordingName: z.string().nullable(),
    startedAt: z.string().nullable(),
    duration: z.number().nullable(),
    completionData: StopRecordingResponseSchema.nullable(),
});

export type RecordingInfo = z.infer<typeof RecordingInfoSchema> & {
    takeStates: Record<string, GroupTakeState>;  // the take_state of each group in the last app state
    endedTake: EndedTakeNotice | null;           // a take that ended by itself with an error (camera-requests.md 8.4)
};
