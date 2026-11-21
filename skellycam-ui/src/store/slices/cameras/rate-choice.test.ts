// Run: node --experimental-strip-types --test src/store/slices/cameras/rate-choice.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeFramerate } from './rate-choice.ts';

test('a stored "auto" rate (-1 or 0) loads as 30, so saved and new cameras request one rate (camera-requests.md 2.2, 2.8)', () => {
    const stored = (framerate: number) => ({ framerate, exposure: -7 });
    assert.deepEqual(normalizeFramerate(stored(-1)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(0)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(30)), stored(30));
    assert.deepEqual(normalizeFramerate(stored(60)), stored(60));
    const partial: { exposure: number; framerate?: number } = { exposure: -7 };
    assert.deepEqual(normalizeFramerate(partial), { exposure: -7 }, 'no stored rate: the default applies');
});
