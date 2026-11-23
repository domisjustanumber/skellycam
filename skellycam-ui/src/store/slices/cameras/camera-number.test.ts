// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-number.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { applyRequestBody, withDetectionNumbers } from './camera-number.ts';

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

test('the apply request body holds the numbers and the names of the current detection', () => {
    assert.deepEqual(applyRequestBody({ a1b2: stored }, [{ id: 'a1b2', index: 2, name: 'Logitech C922' }]), {
        camera_configs: { a1b2: { ...stored, camera_index: 2, camera_name: 'Logitech C922' } },
        retry_camera_ids: [],
    });
});

test('windows-capture.md 8.3 (ADR-Z7F3): only "Update Cameras" names failed cameras to open again', () => {
    assert.deepEqual(applyRequestBody({ a1b2: stored }, [], ['a1b2']).retry_camera_ids, ['a1b2']);
    const thunks = readFileSync(new URL('./cameras-thunks.ts', import.meta.url), 'utf8');
    assert.match(thunks, /kind = 'settings', retry = \[\] \}/, 'an apply with no retry list restarts no camera');
    assert.match(thunks, /applyConfigs\(configs, getState\(\)\.cameras\.cameras, retry\)/);
    assert.match(thunks, /applyConfigs\(all, getState\(\)\.cameras\.cameras\)/, 'the close-all fall back makes a new group: no retry');
    const panel = readFileSync(new URL('../../../components/camera-config-tree-view/CameraConfigSidebarPanel.tsx', import.meta.url), 'utf8');
    assert.match(panel, /camerasConnectOrUpdate\(\{ configs, kind: 'update-cameras', retry: changes\.retry \}\)/);
    assert.equal((panel.match(/retry:/g) ?? []).length, 1, 'no other apply of the panel sends a retry list');
});

test('the Auto choice goes on the wire as AUTO (the exposure search of the server, camera-requests.md 1.5); MANUAL is unchanged', () => {
    const cameras = [{ id: 'a', index: 0, name: 'A' }, { id: 'm', index: 1, name: 'M' }];
    const auto = { camera_id: 'a', camera_index: 0, camera_name: 'A', exposure_mode: 'AUTO', exposure: -7 };
    const manual = { camera_id: 'm', camera_index: 1, camera_name: 'M', exposure_mode: 'MANUAL', exposure: -6 };
    const body = applyRequestBody({ a: auto, m: manual }, cameras);
    assert.deepEqual(body.camera_configs.a, auto);
    assert.deepEqual(body.camera_configs.m, manual);
    assert.doesNotMatch(readFileSync(new URL('./camera-number.ts', import.meta.url), 'utf8'), /RECOMMEND|shortcut:/);
});

test('the apply thunk sends the body of applyRequestBody', () => {
    const thunks = readFileSync(new URL('./cameras-thunks.ts', import.meta.url), 'utf8');
    assert.match(thunks, /const request(: \w+)? = applyRequestBody\(configs, cameras, retry\);/);
    assert.match(thunks, /applyConfigs\(configs, getState\(\)\.cameras\.cameras, retry\)/);
    assert.match(thunks, /applyConfigs\(all, getState\(\)\.cameras\.cameras\)/, 'the fall back sends the detection numbers too');
    assert.match(thunks, /body: JSON\.stringify\(request\)/);
});
