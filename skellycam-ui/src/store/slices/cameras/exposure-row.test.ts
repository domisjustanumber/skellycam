// Run: node --experimental-strip-types --test src/store/slices/cameras/exposure-row.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { anyAdjusting, copyHeldValues, exposureRowText, normalizeExposureMode, searchBlocked, serverModeRate, serverStatusOf } from './exposure-row.ts';

test('T-REQ-70: a stored RECOMMEND loads as AUTO; AUTO and MANUAL stay; the other fields do not change', () => {
    const stored = (exposure_mode: string) => ({ exposure_mode, exposure: -8, resolution: { width: 1280, height: 720 } });
    assert.deepEqual(normalizeExposureMode(stored('RECOMMEND')), stored('AUTO'));
    assert.deepEqual(normalizeExposureMode(stored('AUTO')), stored('AUTO'));
    assert.deepEqual(normalizeExposureMode(stored('MANUAL')), stored('MANUAL'));
});

test('a stored config with no exposure_mode stays as it is', () => {
    const partial: { exposure: number; exposure_mode?: string } = { exposure: -7 };
    assert.deepEqual(normalizeExposureMode(partial), { exposure: -7 });
});

const en: Record<string, string> = JSON.parse(readFileSync(new URL('../../../i18n/locales/en-english.json', import.meta.url), 'utf8'));
const texts = (row: { chip: string | null; keys: string[] }) => [row.chip, ...row.keys.map(key => en[key])].filter(Boolean);

test('T-REQ-27: the exposure row texts of 1.8, to the character; no "Found at" text', () => {
    const manual = { exposure_mode: 'MANUAL', exposure: -8, exposure_found_at_fps: null };
    const auto = { exposure_mode: 'AUTO', exposure: -8, exposure_found_at_fps: 30 };
    const unset = { exposure_mode: 'AUTO', exposure: -7, exposure_found_at_fps: null };
    assert.deepEqual(texts(exposureRowText(manual, 30, 'ready', [], 30)), ['E:-8']);
    assert.deepEqual(texts(exposureRowText(auto, 30, 'ready', [], 30)), ['E:-8 auto']);
    assert.deepEqual(texts(exposureRowText(unset, 30, 'ready', [], 30)), ['Auto: no value found yet']);
    assert.deepEqual(texts(exposureRowText(auto, 30, 'adjusting', [], null)), ['E:-8 auto', 'Setting exposure…']);
    assert.deepEqual(texts(exposureRowText(manual, 30, 'too_slow', [], 25.76)), ['E:-8', 'Camera is slow. Try adding more light']);
    assert.deepEqual(texts(exposureRowText(auto, 30, 'too_slow', [], 25.76)), ['E:-8 auto', 'Camera is slow. Try adding more light']);
    assert.deepEqual(texts(exposureRowText(manual, 30, 'too_slow', [], 31.42)), ['E:-8', 'The camera delivers more frames than its mode rate']);
    assert.deepEqual(texts(exposureRowText(auto, 30, 'ready', [{ kind: 'add_light' }], 30)), ['E:-8 auto', 'Add light']);
    assert.deepEqual(texts(exposureRowText(manual, 30, 'ready', [{ kind: 'exposure_search_failed' }], 30)), ['E:-8', 'Exposure search failed']);
    assert.deepEqual(texts(exposureRowText(manual, 30, 'ready', [{ kind: 'exposure_clamped' }], 30)), ['E:-8', 'The longest manual exposure is -5. The camera uses -5.']);
    assert.deepEqual(texts(exposureRowText(auto, 30, 'ready', [{ kind: 'no_manual_exposure' }], 30)), ['No manual exposure on this camera']);
    assert.ok(!JSON.stringify(en).includes('Found at'));
});

test('T-REQ-49: copyHeldValues copies only a camera whose search is done; running, failed and MANUAL stay', () => {
    const desired = {
        run: { exposure_mode: 'AUTO', exposure: -7, exposure_found_at_fps: null },
        done: { exposure_mode: 'AUTO', exposure: -7, exposure_found_at_fps: null },
        fail: { exposure_mode: 'AUTO', exposure: -7, exposure_found_at_fps: 30 },
        man: { exposure_mode: 'MANUAL', exposure: -6, exposure_found_at_fps: null },
    };
    const server = (state: string, mode = 'AUTO') => ({ status: { exposure_search: { state } }, mode });
    const cameras = { run: server('running'), done: server('done'), fail: server('failed'), man: server('done', 'MANUAL') };
    const group = {
        configs: Object.fromEntries(Object.entries(cameras).map(([id, c]) => [id, { exposure_mode: c.mode, exposure: -9, exposure_found_at_fps: 30 }])),
        cameras: Object.fromEntries(Object.entries(cameras).map(([id, c]) => [id, { status: c.status }])),
    };
    const result = copyHeldValues(desired, { camera_groups: { g: group } });
    assert.deepEqual(result.done, { exposure_mode: 'AUTO', exposure: -9, exposure_found_at_fps: 30 });
    assert.equal(result.run, desired.run);
    assert.equal(result.fail, desired.fail);
    assert.equal(result.man, desired.man);
    assert.equal(copyHeldValues(result, { camera_groups: { g: group } }), result, 'no change: the same object');
});

test('the record button waits while a camera is adjusting; serverStatusOf finds the camera in its group', () => {
    const group = (state: string) => ({ configs: { a: { exposure: -7 } }, cameras: { a: { status: { state } } } });
    assert.equal(anyAdjusting([group('ready'), group('adjusting')]), true);
    assert.equal(anyAdjusting([group('ready'), { configs: {} }]), false);
    assert.equal(serverStatusOf([group('checking')], 'a')?.state, 'checking');
    assert.equal(serverStatusOf([group('checking')], 'b'), undefined);
});

test('the search buttons wait while a camera starts, waits or searches; the mode rate comes from the server', () => {
    const group = (state: string, extra = {}) => ({ configs: { a: { exposure: -7, framerate: 30 } }, cameras: { a: { status: { state, ...extra } } } });
    for (const state of ['starting', 'waiting', 'adjusting']) assert.equal(searchBlocked([group(state)]), true, state);
    for (const state of ['ready', 'too_slow', 'checking', 'failed']) assert.equal(searchBlocked([group(state)]), false, state);
    assert.equal(serverModeRate([group('ready', { mode: { fps_num: 30000, fps_den: 1001 } })], 'a', 60), 30000 / 1001);
    assert.equal(serverModeRate([group('ready')], 'a', 60), 30);
    assert.equal(serverModeRate([], 'a', 60), 60);
});
