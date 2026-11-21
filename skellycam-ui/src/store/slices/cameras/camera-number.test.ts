// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-number.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { withDetectionNumbers } from './camera-number.ts';

const stored = { camera_id: 'a1b2', camera_index: 0, camera_name: 'Old name', exposure: -7, use_this_camera: true };

test('T-REQ-60: the request config gets the number and the name of the current detection', () => {
    const cameras = [{ id: 'a1b2', index: 2, name: 'Logitech C922' }];
    assert.deepEqual(withDetectionNumbers({ a1b2: stored }, cameras), {
        a1b2: { ...stored, camera_index: 2, camera_name: 'Logitech C922' },
    });
    assert.equal(stored.camera_index, 0, 'the stored config does not change');
});

test('a camera that is not in the current detection keeps its number and name', () => {
    assert.deepEqual(withDetectionNumbers({ a1b2: stored }, [{ id: 'ffff', index: 2, name: 'Other' }]), { a1b2: stored });
});
