// Run: node --experimental-strip-types --test src/store/slices/cameras/rate-choice.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import {
    chosenRate, groupRate, nextRateChecking, normalizeFramerate, rateCheckingAtResponse, rateChoice, rateFallbackText,
    rateRequestConfigs, replacesDesired, withChosenRate,
} from './rate-choice.ts';

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

test('T-REQ-87: rateChoice with no modes, and the reason of 59.94 against 60 (camera-requests.md 2.8)', () => {
    assert.deepEqual(rateChoice([camera(1, [])]), { can60: false, reasons: ['Camera 1 · Cam A has no 60 fps mode at 1280x720'] });
    assert.deepEqual(rateChoice([camera(1, undefined)]).reasons, ['Camera 1 · Cam A has no 60 fps mode at 1280x720']);
    const ntsc: Modes = [{ width: 1280, height: 720, framerates: [59.94] }];
    assert.deepEqual(rateChoice([camera(1, ntsc), camera(2, both)]),
        { can60: false, reasons: ['Camera 1 · Cam A has 59.94 fps, not 60 fps, at 1280x720'] });
});

test('T-REQ-88: chosenRate is the rate of the first selected camera, else of the first camera (camera-requests.md 2.8)', () => {
    const at = (framerate: number, selected = true) => camera(1, both, undefined, framerate, selected);
    assert.equal(chosenRate([at(30, false), at(60)]), 60);
    assert.equal(chosenRate([at(59.94)]), 60);
    assert.equal(chosenRate([at(60, false), at(30)]), 30);
    assert.equal(chosenRate([at(29.97)]), 30);
    assert.equal(chosenRate([at(60, false), at(30, false)]), 60, 'no selected camera: the first camera');
    assert.equal(chosenRate([]), 30);
});

test('T-REQ-89: rateRequestConfigs sends the applied config of each camera of the group with the new rate (camera-requests.md 2.8)', () => {
    const config = (id: string, framerate = 30, exposure = -8) => ({ camera_id: id, use_this_camera: true, framerate, exposure });
    // The list has a pending edit of A (-5), B unticked but still in the group, and C ticked but not in the group:
    // the request holds only the applied configs of the group, A and B.
    const group = { a: config('a'), b: config('b') };
    assert.deepEqual(rateRequestConfigs(group, 60), { a: config('a', 60), b: config('b', 60) });
    assert.deepEqual(group, { a: config('a'), b: config('b') }, 'the applied configs do not change');
});

test('T-REQ-90: rateFallbackText reads the live state; nextRateChecking ends when no camera is busy and no apply runs (camera-requests.md 2.8)', () => {
    const fallback = { kind: 'rate_fallback', text: 'The group runs at 30 fps. Camera a measured 29.66 fps in its 60 fps mode at exposure -7.' };
    const group = (state: string, warnings: { kind: string; text: string }[] = []) => [{ configs: { a: {} }, cameras: { a: { status: { state, warnings } } } }];
    assert.equal(rateFallbackText(group('ready')), null);
    assert.equal(rateFallbackText(group('ready', [fallback])), fallback.text);
    assert.equal(rateFallbackText(group('ready', [{ kind: 'add_light', text: 'add light' }])), null);
    assert.equal(nextRateChecking(false, true, false, true), true, 'a new fall back item while a camera is busy');
    assert.equal(nextRateChecking(false, false, false, true), false, 'a new fall back item with no busy camera: no state comes to end it');
    assert.equal(nextRateChecking(true, true, false, false), true, 'a camera is busy');
    assert.equal(nextRateChecking(true, false, true, false), true, 'the apply of the pick runs');
    assert.equal(nextRateChecking(true, false, false, false), false, 'no camera is busy, and no apply runs');
    assert.equal(nextRateChecking(false, true, false, false), false, 'a later search on request, with an old item');
    // The response of a pick: a camera in AUTO searches after it, so the next live state decides
    assert.equal(rateCheckingAtResponse(true, true, false), true, 'AUTO: the last live state is from before the reopen');
    assert.equal(rateCheckingAtResponse(true, false, false), false, 'MANUAL: the apply waited for the rate check');
    assert.equal(rateCheckingAtResponse(true, false, true), true, 'MANUAL: the last live state still shows a busy camera');
    // The revert of a failed pick: the rate of the group in the live state at the failure, else the rate before
    assert.equal(groupRate({ a: { framerate: 29.97 } }, 60), 30);
    assert.equal(groupRate({ a: { framerate: 60 } }, 30), 60);
    assert.equal(groupRate({}, 60), 60);
});

test('T-REQ-98: the response of a pick does not replace the desired configs (camera-requests.md 2.8)', () => {
    assert.equal(replacesDesired('rate', true), false, 'a pick keeps the unapplied edits');
    assert.equal(replacesDesired('settings', true), true);
    assert.equal(replacesDesired('update-cameras', false), false, 'a camera that the request did not send');
});

test('T-REQ-95: withChosenRate gives each detected camera the current choice (camera-requests.md 2.8)', () => {
    const cam = (framerate: number, selected = true) => ({ selected, desiredConfig: { framerate, exposure: -7 } });
    assert.deepEqual(withChosenRate([cam(60)], [cam(30), cam(30, false)]), [cam(60), cam(60, false)]);
    assert.deepEqual(withChosenRate([], [cam(30, false), cam(60), cam(30)]), [cam(60, false), cam(60), cam(60)],
        'no list before: the rate of the first selected camera of the new list');
});
