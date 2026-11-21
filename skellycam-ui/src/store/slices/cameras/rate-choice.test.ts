// Run: node --experimental-strip-types --test src/store/slices/cameras/rate-choice.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { checkingRate, chosenRate, normalizeFramerate, rateChoice, rateFallbackText, rateRequestConfigs } from './rate-choice.ts';

test('a stored "auto" rate (-1 or 0) loads as 30, so saved and new cameras request one rate (camera-requests.md 2.2, 2.8)', () => {
    const stored = (framerate: number) => ({ framerate, exposure: -7 });
    assert.deepEqual(normalizeFramerate(stored(-1)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(0)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(30)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(60)), stored(60));
    const partial: { exposure: number; framerate?: number } = { exposure: -7 };
    assert.deepEqual(normalizeFramerate(partial), { exposure: -7 }, 'no stored rate: the default applies');
});

type Modes = { width: number; height: number; framerates: number[] }[];

const camera = (index: number, modes: Modes | undefined, size = { width: 1280, height: 720 }, framerate = 30, selected = true) => ({
    id: `c${index}`, index, name: `Cam ${'ABC'[index - 1]}`, selected,
    desiredConfig: { framerate, resolution: size },
    deviceInfo: { supportedModes: modes },
});
const both: Modes = [{ width: 1920, height: 1080, framerates: [30] }, { width: 1280, height: 720, framerates: [30, 60] }];

test('T-REQ-38: rateChoice offers 60 fps only when each selected camera has 60 at its size (camera-requests.md 2.5)', () => {
    assert.deepEqual(rateChoice([camera(1, both), camera(2, both)]), { can60: true, reasons: [] });
    const big = rateChoice([camera(1, both), camera(2, both, { width: 1920, height: 1080 })]);
    assert.equal(big.can60, false);
    assert.deepEqual(big.reasons, ['Camera 2 · Cam B has no 60 fps mode at 1920x1080']);
    const ntsc: Modes = [{ width: 1280, height: 720, framerates: [30, 59.94] }];
    assert.equal(rateChoice([camera(1, ntsc), camera(2, both)]).can60, false);
    assert.deepEqual(rateChoice([camera(1, both, undefined, 30, false)]), { can60: false, reasons: [] });
    assert.deepEqual(rateChoice([camera(1, ntsc), camera(2, ntsc)]), { can60: true, reasons: [] }, '59.94 with 59.94 is one rate (D17)');
});

test('T-REQ-80: rateChoice with no modes, and the reason of 59.94 against 60 (camera-requests.md 2.8)', () => {
    assert.deepEqual(rateChoice([camera(1, [])]), { can60: false, reasons: ['Camera 1 · Cam A has no 60 fps mode at 1280x720'] });
    assert.deepEqual(rateChoice([camera(1, undefined)]).reasons, ['Camera 1 · Cam A has no 60 fps mode at 1280x720']);
    const ntsc: Modes = [{ width: 1280, height: 720, framerates: [59.94] }];
    assert.deepEqual(rateChoice([camera(1, ntsc), camera(2, both)]),
        { can60: false, reasons: ['Camera 1 · Cam A has 59.94 fps, not 60 fps, at 1280x720'] });
});

test('T-REQ-81: chosenRate is the rate of the first selected camera, else of the first camera (camera-requests.md 2.8)', () => {
    const at = (framerate: number, selected = true) => camera(1, both, undefined, framerate, selected);
    assert.equal(chosenRate([at(30, false), at(60)]), 60);
    assert.equal(chosenRate([at(59.94)]), 60);
    assert.equal(chosenRate([at(60, false), at(30)]), 30);
    assert.equal(chosenRate([at(29.97)]), 30);
    assert.equal(chosenRate([at(60, false), at(30, false)]), 60, 'no selected camera: the first camera');
    assert.equal(chosenRate([]), 30);
});

test('T-REQ-82: rateRequestConfigs sends each camera of the group with the new rate, and no other camera (camera-requests.md 2.8)', () => {
    const config = (id: string, use: boolean, framerate = 30) => ({ camera_id: id, use_this_camera: use, framerate, exposure: -8 });
    const cameras = [
        { id: 'a', desiredConfig: config('a', true) },
        { id: 'b', desiredConfig: config('b', false) },  // unticked, still in the group: "Update Cameras" closes it
        { id: 'c', desiredConfig: config('c', true) },   // ticked, not in the group: "Update Cameras" adds it
    ];
    const group = { a: config('a', true), b: config('b', true) };
    assert.deepEqual(rateRequestConfigs(cameras, group, 60), { a: config('a', true, 60), b: config('b', true, 60) });
});

test('T-REQ-83: rateFallbackText and checkingRate read the live state (camera-requests.md 2.8)', () => {
    const fallback = { kind: 'rate_fallback', text: 'The group runs at 30 fps. Camera a measured 29.66 fps in its 60 fps mode at exposure -7.' };
    const group = (state: string, warnings: { kind: string; text: string }[] = []) => [{ configs: { a: {} }, cameras: { a: { status: { state, warnings } } } }];
    assert.equal(rateFallbackText(group('ready')), null);
    assert.equal(rateFallbackText(group('ready', [fallback])), fallback.text);
    assert.equal(rateFallbackText(group('ready', [{ kind: 'add_light', text: 'add light' }])), null);
    assert.equal(checkingRate(group('adjusting'), 60), true);
    assert.equal(checkingRate(group('adjusting'), 30), false);
    assert.equal(checkingRate(group('starting', [fallback]), 30), true, 'the reopen of a fall back');
    assert.equal(checkingRate(group('ready', [fallback]), 30), false);
});
