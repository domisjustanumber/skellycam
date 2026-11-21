// Run: node --experimental-strip-types --test src/store/slices/cameras/exposure-row.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeExposureMode } from './exposure-row.ts';

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
