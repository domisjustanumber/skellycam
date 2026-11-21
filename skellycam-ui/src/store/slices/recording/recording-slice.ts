import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { RecordingInfo, StopRecordingResponseSchema } from './recording-types';
import { startRecording, stopRecording } from './recording-thunks';
import { serverStateReceived, serverDisconnected } from '../connection/connection-slice';
import { endedTakeNotice } from './ended-take';

const initialState: RecordingInfo = {
    isRecording: false,
    recordingDirectory: '~/skellycam_data/recordings',
    recordingName: null,
    startedAt: null,
    duration: 0,
    completionData: null,
    takeStates: {},
    endedTake: null,
};

export const recordingSlice = createSlice({
    name: 'recording',
    initialState,
    reducers: {
        recordingInfoUpdated: (state, action: PayloadAction<Partial<RecordingInfo>>) => {
            return { ...state, ...action.payload };
        },
        recordingDirectoryChanged: (state, action: PayloadAction<string>) => {
            state.recordingDirectory = action.payload;
        },
        recordingDurationUpdated: (state, action: PayloadAction<number>) => {
            state.duration = action.payload;
        },
        recordingCompletionDismissed: (state) => {
            state.completionData = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(startRecording.fulfilled, (state, action) => {
                state.isRecording = true;
                state.recordingName = action.meta.arg.recordingName;
                state.recordingDirectory = action.meta.arg.recordingDirectory;
                state.startedAt = new Date().toISOString();
                state.duration = 0;
                state.completionData = null;
                state.endedTake = null;
            })
            .addCase(stopRecording.fulfilled, (state, action) => {
                state.isRecording = false;
                state.recordingName = null;
                state.startedAt = null;
                state.duration = 0;
                state.completionData = action.payload ?? null;
            })
            // Reconcile recording state from the authoritative server snapshot.
            .addCase(serverStateReceived, (state, action) => {
                const groups = action.payload.state.camera_groups;
                state.isRecording = Object.values(groups).some(group => group.recording_in_progress);
                // A take that ended by itself with an error: Start again, the error and the summary at once, no stop
                // request (camera-requests.md 8.4). With no take_state from the server nothing changes.
                const notice = endedTakeNotice(state.takeStates, groups);
                state.takeStates = Object.fromEntries(Object.entries(groups).map(([id, group]) => [id, { take_state: group.take_state }]));
                if (notice) {
                    state.isRecording = false;
                    state.recordingName = null;
                    state.startedAt = null;
                    state.duration = 0;
                    const summary = StopRecordingResponseSchema.safeParse(notice.summary);
                    state.completionData = summary.success ? summary.data : null;
                    state.endedTake = notice;
                } else if (state.endedTake && groups[state.endedTake.groupId]?.take_state !== 'ended_with_error') {
                    state.endedTake = null;  // a new take, the stop request of 8.2, or the group closed
                }
            })
            // On websocket disconnect, clear active-recording state.
            .addCase(serverDisconnected, (state) => {
                state.isRecording = false;
                state.recordingName = null;
                state.startedAt = null;
                state.duration = 0;
            });
    },
});

export const {
    recordingInfoUpdated,
    recordingDirectoryChanged,
    recordingDurationUpdated,
    recordingCompletionDismissed,
} = recordingSlice.actions;
