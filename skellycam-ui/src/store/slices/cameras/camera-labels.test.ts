// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-labels.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { withCameraLabels } from './camera-labels.ts';

const cameras = [
    { id: 'c3c6', index: 1, name: 'USB Camera' },
    { id: '0a1b', index: 5, name: 'Kiyo Pro' },
];

test('each known camera id becomes the camera list label', () => {
    assert.equal(
        withCameraLabels('Failed to start recording: A recording needs each selected camera ready: camera c3c6 is failed; camera 0a1b is starting', cameras),
        'Failed to start recording: A recording needs each selected camera ready: Camera 1 (USB Camera) is failed; Camera 5 (Kiyo Pro) is starting',
    );
    assert.equal(withCameraLabels('camera 0a1b: no mode at the floor', cameras), 'Camera 5 (Kiyo Pro): no mode at the floor');
});

test('an unknown id and other text stay as they are', () => {
    assert.equal(withCameraLabels('camera ffff is failed', cameras), 'camera ffff is failed');
    assert.equal(withCameraLabels('open: device busy', cameras), 'open: device busy');
    assert.equal(withCameraLabels('each selected camera ready', cameras), 'each selected camera ready');
});
