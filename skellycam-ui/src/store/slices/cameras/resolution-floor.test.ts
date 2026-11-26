// Run: node --experimental-strip-types --test src/store/slices/cameras/resolution-floor.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { sizeAtFloor, trackingLimited } from './resolution-floor.ts';

const en: Record<string, string> = JSON.parse(readFileSync(new URL('../../../i18n/locales/en-english.json', import.meta.url), 'utf8'));

test('T-CAP-165: the size floor of the UI is 640 wide and 360 high (windows-capture.md 22.2, Q887 to Q889)', () => {
    for (const [width, height] of [[640, 480], [640, 360], [1280, 720], [1920, 1080]]) {
        assert.equal(sizeAtFloor(width, height), true, `${width}x${height}`);
    }
    for (const [width, height] of [[320, 240], [424, 240], [480, 360], [639, 480], [640, 359]]) {
        assert.equal(sizeAtFloor(width, height), false, `${width}x${height}`);
    }
});

test('T-CAP-165: the tracking note shows below 1280x720 and does not show from 1280x720 (22.2, Q888)', () => {
    for (const [width, height] of [[640, 480], [640, 360], [1279, 720], [1280, 719]]) {
        assert.equal(trackingLimited(width, height), true, `${width}x${height}`);
    }
    for (const [width, height] of [[1280, 720], [1920, 1080]]) {
        assert.equal(trackingLimited(width, height), false, `${width}x${height}`);
    }
    assert.equal(en.trackingLimitedByResolution,
        'Hand and face tracking will be limited at this resolution. 1280 × 720 or more gives the best tracking.');
});
