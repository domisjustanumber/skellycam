// T-PRV-42: the product code reads no canvas back [T, player 8.3] (specs/preview-4b.md 5.4, 7.4). A guard: it can
// pass before the 4b code.
import assert from 'node:assert/strict';
import {readdirSync, readFileSync, statSync} from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const NAMES = /\b(getImageData|toDataURL|toBlob|readPixels)\b/;

function productFiles(dir: string): string[] {
    return readdirSync(dir).flatMap(name => {
        const full = path.join(dir, name);
        if (statSync(full).isDirectory()) return name === 'tests' || name === 'node_modules' ? [] : productFiles(full);
        return /\.(ts|tsx|js|jsx|mts)$/.test(name) ? [full] : [];
    });
}

test('T-PRV-42 the product code of skellycam-ui/src reads no canvas back', () => {
    assert.ok(path.basename(SRC) === 'src', `the search root is ${SRC}`);
    const hits = productFiles(SRC)
        .filter(file => NAMES.test(readFileSync(file, 'utf8')))
        .map(file => path.relative(SRC, file).split(path.sep).join('/'));
    assert.deepEqual(hits, []);
});
