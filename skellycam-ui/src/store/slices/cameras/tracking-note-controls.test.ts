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

test('T-CAP-165: a custom size below the floor puts the applied size back in the fields (22.2 [YQN1 5])', () => {
    const text = source('components/camera-config-panel/CameraConfigResolution.tsx');
    assert.match(text, /sizeAtFloor\(w, h\)\)[\s\S]*?\} else \{[\s\S]*?setCustomWidth\(resolution\.width\.toString\(\)\)/);
});
