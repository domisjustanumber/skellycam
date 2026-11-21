// Run: node --experimental-strip-types --test src/store/slices/recording/ended-take.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { endedTakeNotice, takeErrorText } from './ended-take.ts';

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
