// The test Vite config of the player harness (specs/player.md section 12.1): it builds the harness main
// process, its preload script, the bare harness page, the host-view page and the page `preview` of the step 4b
// preview (specs/preview-4b.md 7.2) into dist-player-harness/.
// A product module that does not exist yet becomes a module that throws "product module missing" when
// it loads, so the harness builds and launches, and each test fails on its own.
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vite';
import type {Plugin} from 'vite';
import react from '@vitejs/plugin-react';
import electron from 'vite-plugin-electron/simple';

const UI = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(UI, 'src');
const OUT = path.join(UI, 'dist-player-harness');
const HARNESS = path.join(SRC, 'player', 'tests', 'harness');
const MISSING = '\0player-harness-missing:';

function missingProduct(): Plugin {
    return {
        name: 'player-harness-missing-product',
        enforce: 'pre',
        async resolveId(source, importer, options) {
            if (!importer || !(source.startsWith('.') || source.startsWith('@/'))) return null;
            const abs = source.startsWith('@/') ? path.join(SRC, source.slice(2)) : path.resolve(path.dirname(importer), source);
            if (!abs.startsWith(SRC + path.sep) || /[\\/]tests[\\/]/.test(abs)) return null;
            const candidates = [abs, `${abs}.ts`, `${abs}.tsx`];
            if (candidates.some(existsSync)) return this.resolve(source, importer, {...options, skipSelf: true});
            return MISSING + path.relative(UI, abs).split(path.sep).join('/');
        },
        load(id) {
            if (id.startsWith(MISSING)) return `throw new Error(${JSON.stringify(`product module missing: ${id.slice(MISSING.length)}`)});\nexport {};\n`;
            return null;
        },
    };
}

export default defineConfig({
    root: SRC,
    base: './',
    resolve: {alias: {'@': SRC}},
    plugins: [
        missingProduct(),
        react(),
        electron({
            main: {
                entry: path.join(HARNESS, 'main.ts'),
                vite: {plugins: [missingProduct()], build: {outDir: path.join(OUT, 'main'), emptyOutDir: true, minify: false}},
            },
            preload: {
                input: path.join(HARNESS, 'preload.ts'),
                vite: {plugins: [missingProduct()], build: {outDir: path.join(OUT, 'preload'), emptyOutDir: true, minify: false, modulePreload: false}},
            },
        }),
    ],
    build: {
        outDir: path.join(OUT, 'renderer'),
        emptyOutDir: true,
        minify: false,
        rollupOptions: {
            input: {
                harness: path.join(HARNESS, 'index.html'),
                host: path.join(SRC, 'components', 'playback', 'tests', 'host', 'index.html'),
                preview: path.join(SRC, 'components', 'camera-views', 'tests', 'harness', 'preview', 'index.html'),
            },
        },
    },
});
