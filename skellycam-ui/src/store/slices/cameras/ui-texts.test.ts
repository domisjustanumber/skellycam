// Run: node --experimental-strip-types --test src/store/slices/cameras/ui-texts.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const en: Record<string, string> = JSON.parse(readFileSync(new URL('../../../i18n/locales/en-english.json', import.meta.url), 'utf8'));

test('the English texts that the user ruled, to the character (ADR-F2KY, camera-requests.md 1.5a and 1.8)', () => {
    assert.equal(en.cameraIsSlow, 'Camera is slow. Try adding more light');
    assert.equal(en.stopRecordingFirst, 'Stop the recording first');
    assert.equal(en.audioNotAvailableYet, 'Audio recording is not available yet.');
});
