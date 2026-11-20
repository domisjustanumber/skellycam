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
    ]), { tooSlow: ['slow'], retry: ['fail', 'dead'], close: ['unticked', 'failoff'], add: ['new'] });
});
