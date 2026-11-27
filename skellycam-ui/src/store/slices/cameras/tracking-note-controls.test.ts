// Run: node --experimental-strip-types --test src/store/slices/cameras/tracking-note-controls.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// No React render in the node unit tests: this test reads the two resolution controls as text.
const source = (path: string) => readFileSync(new URL(`../../../${path}`, import.meta.url), 'utf8');

test('T-CAP-165: each resolution control shows the tracking note and points at it (windows-capture.md 22.2, Q888)', () => {
    for (const path of ['components/camera-config-panel/CameraConfigResolution.tsx',
                        'components/camera-views/CameraGridSettingsModal.tsx']) {
        const text = source(path);
        assert.match(text, /<TrackingNote id=\{(\w+)\}/, `${path} has no TrackingNote`);
        const id = text.match(/<TrackingNote id=\{(\w+)\}/)![1];
        assert.match(text, new RegExp(String.raw`describedBy=\{[^}]*\b${id}\b`), `${path}: the control does not point at the note`);
    }
});

test('T-CAP-165: a custom size below the floor keeps the typed numbers and shows an error line (22.2, Q899)', () => {
    const text = source('components/camera-config-panel/CameraConfigResolution.tsx');
    const en: Record<string, string> = JSON.parse(source('i18n/locales/en-english.json'));
    assert.equal(en.smallestSizeIs640x360, 'The smallest size is 640 × 360');
    assert.match(text, /role="alert"[^>]*>\{t\('smallestSizeIs640x360'\)\}/, 'no error line');
    assert.match(text, /id=\{errorId\}/, 'the error line has no id');
    assert.match(text, /aria-describedby=\{[^}]*errorId/, 'the inputs do not point at the error line');
    assert.doesNotMatch(text, /else \{[^}]*setCustomWidth\(resolution\.width\.toString\(\)\)/, 'a reject must keep the typed numbers');
});

test('T-CAP-165: the error line goes when its cause goes (22.2, Q899)', () => {
    const text = source('components/camera-config-panel/CameraConfigResolution.tsx');
    // a change of the resolution by another control: the effect that puts the applied size in the fields
    assert.match(text, /useEffect\(\(\) => \{\s*setTooSmall\(false\);/, 'the effect of a new resolution keeps the error line');
    // an empty or non-numeric field
    assert.match(text, /if \(isNaN\(w\) \|\| isNaN\(h\)\) \{\s*setTooSmall\(false\);\s*return;/, 'an empty field keeps the error line');
});

test('T-CAP-165: the note and the error line in the three languages of the docs copies, with the numbers of English (22.2, Q900)', () => {
    for (const file of ['es-espanol.json', 'zh-CN-zhongwen.json', 'ar-arabic.json']) {
        const texts: Record<string, string> = JSON.parse(source(`i18n/locales/${file}`));
        assert.ok(texts.trackingLimitedByResolution?.includes('1280 × 720'), `${file}: the note`);
        assert.ok(texts.smallestSizeIs640x360?.includes('640 × 360'), `${file}: the error line`);
    }
});
