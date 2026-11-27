// T-PLAY-35: the boundary rule of specs/player.md section 4.2, and the load of each module file
// outside main/ under Node type stripping.
import assert from 'node:assert/strict';
import {existsSync, readdirSync, readFileSync, statSync} from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath, pathToFileURL} from 'node:url';

const MODULE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const UI = path.resolve(MODULE, '../..');

// The files of section 4.1.
const MODULE_FILES = [
    'index.ts', 'files/take-files.ts', 'files/electron-take-files.ts', 'reader/take.ts', 'reader/manifest.ts',
    'reader/sidecar.ts', 'reader/fit.ts', 'reader/matroska.ts', 'clock/clock.ts', 'clock/choose.ts',
    'tile/tile.ts', 'tile/format.ts', 'main/take-scheme.ts', 'main/bridge.ts', 'main/recent-folders.ts',
];
const PUBLIC = new Set(['index.ts', 'main/take-scheme.ts', 'main/bridge.ts']);

function walk(dir: string, exts: RegExp): string[] {
    if (!existsSync(dir)) return [];
    return readdirSync(dir).flatMap(f => {
        const full = path.join(dir, f);
        if (f === 'node_modules') return [];
        return statSync(full).isDirectory() ? walk(full, exts) : exts.test(f) ? [full] : [];
    });
}

function imports(source: string): {spec: string; typeOnly: boolean}[] {
    const out: {spec: string; typeOnly: boolean}[] = [];
    const text = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    for (const m of text.matchAll(/(?:^|[\n;])\s*(import|export)\s+(type\s+)?(?:[^'";]*?\sfrom\s+)?['"]([^'"]+)['"]/g)) out.push({spec: m[3], typeOnly: !!m[2]});
    for (const m of text.matchAll(/\bimport\(\s*['"]([^'"]+)['"]\s*\)/g)) out.push({spec: m[1], typeOnly: false});
    return out;
}

const rel = (f: string) => path.relative(MODULE, f).split(path.sep).join('/');

test('T-PLAY-35 the boundary rule and the load under type stripping', async () => {
    const missing = MODULE_FILES.filter(f => !existsSync(path.join(MODULE, f)));
    assert.deepEqual(missing, [], 'each module file of section 4.1 exists');

    const problems: string[] = [];
    for (const file of walk(MODULE, /\.(ts|tsx|mts)$/)) {
        const r = rel(file);
        const area = r.startsWith('tests/') ? 'tests' : r.startsWith('main/') ? 'main' : 'core';
        const source = readFileSync(file, 'utf8');
        if (/\benum\s+\w+\s*\{/.test(source)) problems.push(`${r}: enum`);
        if (/\bnamespace\s+\w+\s*\{/.test(source)) problems.push(`${r}: namespace`);
        if (/constructor\s*\([^)]*\b(private|public|protected|readonly)\s+\w+/.test(source)) problems.push(`${r}: parameter property`);
        for (const {spec} of imports(source)) {
            if (spec.startsWith('.')) {
                const target = path.resolve(path.dirname(file), spec);
                if (!target.startsWith(MODULE + path.sep)) problems.push(`${r}: ${spec} is outside the module`);
                if (!spec.endsWith('.ts')) problems.push(`${r}: ${spec} does not name the .ts file`);
                continue;
            }
            const node = spec.startsWith('node:');
            const allowed = area === 'core' ? false
                : area === 'main' ? node || spec === 'electron'
                : node || spec === 'electron' || spec === '@playwright/test';
            if (!allowed) problems.push(`${r}: import of ${spec}`);
        }
    }
    // The rest of the UI imports only index.ts and the two files of main/. Test code outside the
    // module may also import the module's tests folder (the fixtures and the harness).
    const outside = [...walk(path.join(UI, 'src'), /\.(ts|tsx)$/), ...walk(path.join(UI, 'electron'), /\.(ts|tsx)$/)]
        .filter(f => !f.startsWith(MODULE + path.sep));
    for (const file of outside) {
        for (const {spec} of imports(readFileSync(file, 'utf8'))) {
            const target = spec.startsWith('.') ? path.resolve(path.dirname(file), spec)
                : spec.startsWith('@/') ? path.join(UI, 'src', spec.slice(2)) : null;
            if (!target || !target.startsWith(MODULE + path.sep)) continue;
            const r = rel(target).replace(/\.tsx?$/, '') + '.ts';
            const isTestCode = /[\\/]tests[\\/]/.test(file);
            if (!PUBLIC.has(r) && !(isTestCode && r.startsWith('tests/'))) problems.push(`${path.relative(UI, file)}: imports ${r}`);
        }
    }
    assert.deepEqual(problems, []);

    // Each module file outside main/ loads under Node type stripping. A type import without
    // `import type` crashes at load.
    for (const f of MODULE_FILES.filter(f => !f.startsWith('main/'))) await import(pathToFileURL(path.join(MODULE, f)).href);
});
