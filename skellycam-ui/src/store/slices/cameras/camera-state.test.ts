// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-state.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { cameraStatesFromAppState, NOT_IN_GROUP, statusesAfterApply } from './camera-state.ts';

const group = (alive: boolean, cameras: Record<string, { state?: string | null; failure?: { stage: string; reason: string } | null } | null>) => ({
    alive,
    configs: Object.fromEntries(Object.keys(cameras).map(id => [id, {}])),
    cameras: Object.fromEntries(Object.entries(cameras).filter(([, s]) => s !== null)
        .map(([id, status]) => [id, { alive: true, status: status! }])),
});

test('a camera counts as connected in checking, adjusting, too_slow, ready and recording (ruling 2)', () => {
    const states = cameraStatesFromAppState([group(true, {
        a: { state: 'checking' }, b: { state: 'adjusting' }, c: { state: 'too_slow' }, d: { state: 'ready' }, e: { state: 'recording' },
    })]);
    for (const id of ['a', 'b', 'c', 'd', 'e']) {
        assert.equal(states[id].connectionStatus, 'connected', id);
        assert.equal(states[id].inGroup, true, id);
        assert.equal(states[id].failure, undefined, id);
    }
    assert.equal(states.c.state, 'too_slow', 'the state is stored on the camera, not matched in a text (review item 11)');
});

test('a too_slow camera and a checking camera stay connected while another camera of the group failed (group.alive false)', () => {
    const states = cameraStatesFromAppState([group(false, {
        slow: { state: 'too_slow', failure: null },
        check: { state: 'checking' },
        bad: { state: 'failed', failure: { stage: 'open', reason: 'device busy' } },
        gone: { state: 'dead' },
    })]);
    assert.equal(states.slow.connectionStatus, 'connected');
    assert.equal(states.check.connectionStatus, 'connected');
    assert.deepEqual(states.bad, { inGroup: true, connectionStatus: 'error', failure: 'open: device busy', state: 'failed' });
    assert.deepEqual(states.gone, { inGroup: true, connectionStatus: 'error', failure: 'dead', state: 'dead' });
});

test('starting, waiting, an unknown state, a null state and a camera with no process are in the group but not connected', () => {
    const states = cameraStatesFromAppState([group(true, {
        s: { state: 'starting' }, w: { state: 'waiting' }, u: { state: 'some_new_state' }, n: { state: null }, none: null,
    })]);
    for (const id of ['s', 'w', 'u', 'n', 'none']) {
        assert.equal(states[id].connectionStatus, 'available', id);
        assert.equal(states[id].inGroup, true, id);
    }
});

test('a camera in no group is not in the result; NOT_IN_GROUP resets every live field', () => {
    assert.deepEqual(cameraStatesFromAppState([]), {});
    assert.deepEqual(NOT_IN_GROUP, { inGroup: false, connectionStatus: 'available', failure: undefined, state: undefined });
});

test('after an apply: only the sent cameras change; a response never claims a camera streams (review items 7 and 8)', () => {
    const live = (connectionStatus: 'available' | 'connected' | 'error', state?: string, failure?: string) =>
        ({ inGroup: true, connectionStatus, failure, state });
    const cameras = [
        { id: 'slow', ...live('connected', 'too_slow') },      // sent again, now fails
        { id: 'ready', ...live('connected', 'ready') },        // sent: a live change
        { id: 'retry', ...live('error', 'failed', 'open: busy') },  // sent: a retry
        { id: 'new', ...NOT_IN_GROUP },                         // sent: added
        { id: 'other', ...live('connected', 'ready') },        // not sent
        { id: 'closed', ...live('connected', 'ready') },       // sent with use_this_camera false: not in the response
    ];
    const result = statusesAfterApply(cameras, { slow: {}, ready: {}, retry: {}, new: {}, other: {} },
        { slow: { stage: 'warm-up', reason: 'not ready in 15 s' } }, ['slow', 'ready', 'retry', 'new', 'closed']);
    assert.deepEqual(result.slow, { status: { inGroup: true, connectionStatus: 'error', failure: 'warm-up: not ready in 15 s', state: 'failed' }, sent: true },
        'no too_slow line beside the failure');
    assert.deepEqual(result.ready, { status: live('connected', 'ready'), sent: true });
    assert.deepEqual(result.retry, { status: { inGroup: true, connectionStatus: 'available', failure: undefined, state: undefined }, sent: true },
        'restarting: not streaming until the app state says so');
    assert.deepEqual(result.new, { status: { inGroup: true, connectionStatus: 'available', failure: undefined, state: undefined }, sent: true });
    assert.deepEqual(result.other, { status: live('connected', 'ready'), sent: false });
    assert.deepEqual(result.closed, { status: NOT_IN_GROUP, sent: true });
});
