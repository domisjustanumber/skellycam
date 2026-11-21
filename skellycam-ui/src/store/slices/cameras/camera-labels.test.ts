// Run: node --experimental-strip-types --test src/store/slices/cameras/camera-labels.test.ts
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { cameraLabel, labelText, linkChip } from './camera-labels.ts';

const en: Record<string, string> = JSON.parse(readFileSync(new URL('../../../i18n/locales/en-english.json', import.meta.url), 'utf8'));

const cameras = [
    { id: 'c3c6', index: 1, name: 'USB Camera' },
    { id: '0a1b', index: 5, name: 'Kiyo Pro' },
    { id: 'a1b2', index: 2, name: 'Logitech C922' },
];

test('T-REQ-28: the label is "Camera <n> · <name>" (camera-requests.md 1.8)', () => {
    assert.equal(cameraLabel(cameras[2]), 'Camera 2 · Logitech C922');
    assert.equal(labelText('Camera a1b2: add light. ...', cameras), 'Camera 2 · Logitech C922: add light. ...');
});

test('T-REQ-28: each known id becomes the label, and the word camera before it goes', () => {
    assert.equal(
        labelText('Failed to start recording: A recording needs each selected camera ready: camera c3c6 is failed; camera 0a1b is starting', cameras),
        'Failed to start recording: A recording needs each selected camera ready: Camera 1 · USB Camera is failed; Camera 5 · Kiyo Pro is starting',
    );
    assert.equal(labelText('camera 0a1b: no mode at the floor', cameras), 'Camera 5 · Kiyo Pro: no mode at the floor');
    // the plural of the one-rate 422
    assert.equal(labelText('cameras c3c6 and 0a1b at 30 fps', cameras), 'Camera 1 · USB Camera and Camera 5 · Kiyo Pro at 30 fps');
    // the 409 list
    assert.equal(labelText('recording cameras: c3c6, 0a1b', cameras), 'recording cameras: Camera 1 · USB Camera, Camera 5 · Kiyo Pro');
});

test('T-REQ-28: an unknown id and other text stay as they are', () => {
    assert.equal(labelText('camera ffff is failed', cameras), 'camera ffff is failed');
    assert.equal(labelText('open: device busy', cameras), 'open: device busy');
    assert.equal(labelText('each selected camera ready', cameras), 'each selected camera ready');
    assert.equal(labelText('camera c3c6x is failed', cameras), 'camera c3c6x is failed', 'only a whole id');
    assert.equal(labelText('camera c3c6 is failed', []), 'camera c3c6 is failed');
});

test('an id that no camera word leads stays: a bare state, a JSON number, a GUID part, an exit code', () => {
    const cams = [{ id: 'dead', index: 1, name: 'A' }, { id: '1280', index: 2, name: 'B' }, { id: 'f976', index: 3, name: 'C' }, { id: '0001', index: 4, name: 'D' }];
    for (const text of [
        'dead',
        'set mode: no MJPG mode at 1280x720 near 60 fps; the camera has [{"width": 1280, "height": 720, "framerates": [30.0]}]',
        'open: MFCreateDeviceSource failed for /usb#vid_046d&pid_085e&mi_00#7&2a1b3c4d&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}/global',
        'streaming: camera process ended (exit code 0001)',
    ]) assert.equal(labelText(text, cams), text);
    // the server texts that name cameras
    assert.equal(labelText('Camera dead runs at 29.97 fps, camera 1280 at 30 fps. The group runs at 29.97 fps.', cams),
        'Camera 1 · A runs at 29.97 fps, Camera 2 · B at 30 fps. The group runs at 29.97 fps.');
    assert.equal(labelText("all cameras of a group must request one frame rate, or each 'auto': camera dead -1, camera 1280 30", cams),
        "all cameras of a group must request one frame rate, or each 'auto': Camera 1 · A -1, Camera 2 · B 30");
    assert.equal(labelText('cameras dead, 1280 and f976 are not streaming', cams), 'Camera 1 · A, Camera 2 · B and Camera 3 · C are not streaming');
});

test('T-REQ-28: no file imports withCameraLabels', () => {
    const src = new URL('../../../', import.meta.url);
    const hits = (readdirSync(src, { recursive: true }) as string[])
        .map(path => path.replaceAll('\\', '/'))
        .filter(path => /\.tsx?$/.test(path) && !path.endsWith('camera-labels.test.ts'))
        .filter(path => readFileSync(new URL(path, src), 'utf8').includes('withCameraLabels'));
    assert.deepEqual(hits, []);
});

test('T-REQ-59: linkChip gives the chip and the tooltip of 3.5', () => {
    const shown = (info: { virtual?: boolean; usbLink?: string }) => {
        const chip = linkChip(info);
        return chip && [en[chip.text], en[chip.tooltip]];
    };
    assert.deepEqual(shown({ usbLink: 'USB 3' }), ['USB 3', 'Connected at USB 3 speed (5 Gbit/s or more)']);
    assert.deepEqual(shown({ usbLink: 'USB 2' }), ['USB 2', 'Connected at USB 2 speed (480 Mbit/s)']);
    assert.deepEqual(shown({ usbLink: 'USB 1' }), ['USB 1', 'Connected at USB 1 speed (12 Mbit/s or less)']);
    assert.deepEqual(shown({ usbLink: 'unknown' }), ['USB ?', 'SkellyCam could not read the USB link of this camera']);
    assert.deepEqual(shown({ usbLink: 'unknown', virtual: true }), ['virtual', 'A virtual camera: it has no USB link']);
    assert.deepEqual(shown({ virtual: true }), ['virtual', 'A virtual camera: it has no USB link']);
});

test('linkChip shows no chip for a detection with no usb_link (a server older than the field)', () => {
    assert.equal(linkChip({}), null);
});
