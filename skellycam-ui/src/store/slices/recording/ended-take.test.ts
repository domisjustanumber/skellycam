// Run: node --experimental-strip-types --test src/store/slices/recording/ended-take.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { endedTakeNotice, recordingAfterAppState, takeErrorText } from './ended-take.ts';

const cameras = [{ id: 'a1b2', index: 2, name: 'Logitech C922' }, { id: 'c3c6', index: 1, name: 'USB Camera' }];
const summary = { recording_name: 'take_1', number_of_frames: 120 };
const ended = { take_error: 'writer of camera a1b2 stalled for 2.0 s', camera_id: 'a1b2', summary };

test('T-REQ-73: recording, then ended_with_error, the same state again, then none', () => {
    const recording = { g: { take_state: 'recording', ended_take_summary: null } };
    const endedState = { g: { take_state: 'ended_with_error', ended_take_summary: ended } };
    const none = { g: { take_state: 'none', ended_take_summary: null } };

    assert.equal(endedTakeNotice(null, recording), null);
    const notice = endedTakeNotice(recording, endedState);
    assert.deepEqual(notice, { groupId: 'g', takeError: ended.take_error, cameraId: 'a1b2', summary });
    assert.equal(takeErrorText(notice!, cameras), 'writer of Camera 2 · Logitech C922 stalled for 2.0 s');
    assert.equal(endedTakeNotice(endedState, endedState), null, 'one notice for each take');
    assert.equal(endedTakeNotice(endedState, none), null);
});

test('with the server fields absent (today) there is no notice', () => {
    assert.equal(endedTakeNotice({ g: {} }, { g: {} }), null);
    assert.equal(endedTakeNotice(null, {}), null);
});

test('the first state after a reload that is already ended_with_error gives the notice once', () => {
    assert.notEqual(endedTakeNotice(null, { g: { take_state: 'ended_with_error', ended_take_summary: ended } }), null);
});

test('the camera label leads the text when the text does not name the camera; no camera: the text as it is', () => {
    const notice = { groupId: 'g', takeError: 'disk full', cameraId: 'c3c6', summary: null };
    assert.equal(takeErrorText(notice, cameras), 'Camera 1 · USB Camera: disk full');
    assert.equal(takeErrorText({ ...notice, cameraId: null }, cameras), 'disk full');
    assert.equal(takeErrorText({ ...notice, cameraId: 'ffff' }, cameras), 'disk full');
});

const recording = {
    isRecording: true, recordingName: 'take_1', startedAt: '2026-11-20T10:00:00Z', duration: 12,
    completionData: null, takeStates: {}, endedTake: null, recordingDirectory: '/data',
};
const keepSummary = (summary: unknown) => summary as object;

test('reducer: with the fields absent (today) only isRecording follows recording_in_progress', () => {
    const next = { ...recording, ...recordingAfterAppState(recording, { g: { recording_in_progress: true } }, keepSummary) };
    assert.deepEqual({ ...next, takeStates: {} }, recording);
    const stopped = { ...recording, ...recordingAfterAppState(recording, { g: { recording_in_progress: false } }, keepSummary) };
    assert.equal(stopped.isRecording, false);
    assert.equal(stopped.recordingName, 'take_1', 'as before: only a stop response clears the take');
    assert.equal(stopped.endedTake, null);
});

test('reducer: ended_with_error -> Start, the take cleared, the summary set, no stop request; the line stays while the state stays', () => {
    const groups = { g: { recording_in_progress: false, take_state: 'ended_with_error', ended_take_summary: ended } };
    const next = { ...recording, ...recordingAfterAppState({ ...recording, takeStates: { g: { take_state: 'recording' } } }, groups, keepSummary) };
    assert.equal(next.isRecording, false);
    assert.equal(next.recordingName, null);
    assert.equal(next.startedAt, null);
    assert.equal(next.duration, 0);
    assert.deepEqual(next.completionData, summary);
    assert.equal(next.endedTake?.takeError, ended.take_error);
    const again = { ...next, ...recordingAfterAppState(next, groups, keepSummary) };
    assert.equal(again.endedTake, next.endedTake, 'no second notice; the line stays');
    const newTake = { ...again, ...recordingAfterAppState(again, { g: { recording_in_progress: true, take_state: 'recording' } }, keepSummary) };
    assert.equal(newTake.endedTake, null);
    assert.equal(newTake.isRecording, true);
});

test('reducer: a summary that does not parse gives no summary dialog, but the error still shows', () => {
    const groups = { g: { recording_in_progress: false, take_state: 'ended_with_error', ended_take_summary: ended } };
    const next = recordingAfterAppState(recording, groups, () => null);
    assert.equal(next.completionData, null);
    assert.notEqual(next.endedTake, null);
});

test('reducer: a record start that fails and gives the old take again shows no second notice; a new take does', () => {
    const endedA = { g: { recording_in_progress: false, take_state: 'ended_with_error', ended_take_summary: ended } };
    const shown = { ...recording, ...recordingAfterAppState({ ...recording, takeStates: { g: { take_state: 'recording' } } }, endedA, keepSummary) };
    assert.notEqual(shown.endedTake, null);
    const starting = { ...shown, endedTake: null, ...recordingAfterAppState(shown, { g: { recording_in_progress: true, take_state: 'recording' } }, keepSummary) };
    const back = recordingAfterAppState(starting, endedA, keepSummary);
    assert.equal(back.endedTake, undefined, 'no notice of the old take');
    assert.equal(endedTakeNotice(starting.takeStates, endedA), null);
    const endedB = { g: { ...endedA.g, ended_take_summary: { ...ended, summary: { ...summary, recording_name: 'take_2' } } } };
    assert.equal(endedTakeNotice(starting.takeStates, endedB)?.summary, endedB.g.ended_take_summary.summary);
});
