// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-updates.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { pendingCameraChanges } from './camera-updates.ts';

const cam = (id: string, over: object) => ({
    id, selected: true, inGroup: true, connectionStatus: 'connected', deviceInfo: {}, ...over,
});

test('each kind of difference, and none for an open unchanged camera', () => {
    assert.deepEqual(pendingCameraChanges([
        cam('open', {}),
        cam('fail', { connectionStatus: 'error', failure: 'open: device busy' }),
        cam('dead', { connectionStatus: 'error', failure: 'dead' }),
        cam('slow', { connectionStatus: 'error', failure: 'too_slow' }),
        cam('unticked', { selected: false }),
        cam('new', { inGroup: false, connectionStatus: 'available' }),
        cam('virt', { inGroup: false, connectionStatus: 'available', deviceInfo: { virtual: true } }),
        cam('idle', { selected: false, inGroup: false, connectionStatus: 'available' }),
        cam('failoff', { selected: false, connectionStatus: 'error', failure: 'dead' }),
    ]), { tooSlow: ['slow'], retry: ['fail', 'dead'], close: ['unticked', 'failoff'], add: ['new'], renumber: [] });
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
