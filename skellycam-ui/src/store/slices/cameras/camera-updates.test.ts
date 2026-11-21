// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-updates.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { closeAllAndConnect, missingFromGroup, pendingCameraChanges, updateRequestConfigs } from './camera-updates.ts';

const cam = (id: string, over: object) => ({
    id, selected: true, inGroup: true, connectionStatus: 'connected', deviceInfo: {}, ...over,
});

test('each kind of difference, and none for an open unchanged camera', () => {
    assert.deepEqual(pendingCameraChanges([
        cam('open', {}),
        cam('fail', { connectionStatus: 'error', failure: 'open: device busy' }),
        cam('dead', { connectionStatus: 'error', failure: 'dead' }),
        cam('unticked', { selected: false }),
        cam('new', { inGroup: false, connectionStatus: 'available' }),
        cam('virt', { inGroup: false, connectionStatus: 'available', deviceInfo: { virtual: true } }),
        cam('idle', { selected: false, inGroup: false, connectionStatus: 'available' }),
        cam('failoff', { selected: false, connectionStatus: 'error', failure: 'dead' }),
    ]), { retry: ['fail', 'dead'], close: ['unticked', 'failoff'], add: ['new'], renumber: [] });
});

test('T1: a too_slow camera is not a failure: no retry, no remove and re-add (ruling 2)', () => {
    const changes = pendingCameraChanges([cam('slow', { connectionStatus: 'connected', state: 'too_slow' })]);
    assert.deepEqual(changes, { retry: [], close: [], add: [], renumber: [] });
});

test('T1: inGroup undefined (no server state yet) adds the ticked camera; an unticked virtual camera is never sent', () => {
    const changes = pendingCameraChanges([
        cam('fresh', { inGroup: undefined, connectionStatus: 'available' }),
        cam('virt', { selected: false, inGroup: undefined, connectionStatus: 'available', deviceInfo: { virtual: true } }),
    ]);
    assert.deepEqual(changes, { retry: [], close: [], add: ['fresh'], renumber: [] });
});

test('review item 4: a camera of the server group with no row (unplugged, then detected again) is closed', () => {
    const changes = pendingCameraChanges([cam('open', {})], ['open', 'gone']);
    assert.deepEqual(changes.close, ['gone']);
});

test('an open camera whose applied number or name differs from the detection is sent again (camera-requests.md 8.1)', () => {
    const applied = (camera_index: number, camera_name: string) => ({ actualConfig: { camera_index, camera_name } });
    const changes = pendingCameraChanges([
        cam('same', { index: 0, name: 'A', ...applied(0, 'A') }),
        cam('number', { index: 2, name: 'B', ...applied(1, 'B') }),
        cam('name', { index: 3, name: 'C new', ...applied(3, 'C') }),
        cam('unticked', { selected: false, index: 4, name: 'D', ...applied(9, 'D') }),
        cam('out', { inGroup: false, connectionStatus: 'available', index: 5, name: 'E', ...applied(9, 'E') }),
        cam('fail', { connectionStatus: 'error', failure: 'dead', index: 6, name: 'F', ...applied(9, 'F') }),
    ]);
    assert.deepEqual(changes.renumber, ['number', 'name']);
    assert.deepEqual(changes.retry, ['fail'], 'a failed camera is sent once, as a retry');
});

test('T5: the request of "Update Cameras": closes with use_this_camera false, the others with true, an orphan from the group config', () => {
    const config = (id: string, exposure: number) => ({ camera_id: id, use_this_camera: true, exposure });
    const cameras = [
        { id: 'a', desiredConfig: config('a', -7) },
        { id: 'b', desiredConfig: config('b', -6) },
        { id: 'c', desiredConfig: config('c', -5) },
        { id: 'd', desiredConfig: config('d', -4) },
        { id: 'quiet', desiredConfig: config('quiet', -3) },
    ];
    const body = updateRequestConfigs(cameras, { close: ['a', 'gone'], retry: ['b'], add: ['c'], renumber: ['d'] }, { gone: config('gone', -9) });
    assert.deepEqual(body, {
        a: { camera_id: 'a', use_this_camera: false, exposure: -7 },
        gone: { camera_id: 'gone', use_this_camera: false, exposure: -9 },
        b: { camera_id: 'b', use_this_camera: true, exposure: -6 },
        c: { camera_id: 'c', use_this_camera: true, exposure: -5 },
        d: { camera_id: 'd', use_this_camera: true, exposure: -4 },
    });
});

test('T5: the fall back (close all, then connect the selected) runs only when a camera sent to open is not in the response', () => {
    const sent = { a: { use_this_camera: true }, b: { use_this_camera: false }, c: { use_this_camera: true } };
    assert.deepEqual(missingFromGroup(sent, { a: {}, c: {} }), []);
    assert.deepEqual(missingFromGroup(sent, { a: {} }), ['c']);
    assert.deepEqual(missingFromGroup({ b: { use_this_camera: false } }, {}), [], 'a close-only request (untick all) needs no fall back');
});

test('the close-all fall back runs only for a call meant to add cameras: "Update Cameras" and Connect with no group', () => {
    const sent = { a: { use_this_camera: true }, n: { use_this_camera: true } };
    const leftOut = { a: {} };   // the server left out the new camera n
    const allIn = { a: {}, n: {} };
    assert.equal(closeAllAndConnect('update-cameras', sent, leftOut), true);
    assert.equal(closeAllAndConnect('connect', sent, leftOut), true);
    assert.equal(closeAllAndConnect('settings', sent, leftOut), false, 'a settings apply stays a live change');
    for (const kind of ['update-cameras', 'connect', 'settings'] as const) {
        assert.equal(closeAllAndConnect(kind, sent, allIn), false, kind);
    }
});
