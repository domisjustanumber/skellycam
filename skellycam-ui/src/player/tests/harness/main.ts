// The main process of the test Electron app (specs/player.md section 12.1). It installs the take
// handler with a temporary recordings folder and picked-folders file, and gives the tests two hooks
// through `globalThis.__harness` (Playwright `electronApp.evaluate`): a dialog pick and a read fault.
// A missing product module is recorded, and the window still opens, so each test fails on its own.
import {app, BrowserWindow, ipcMain, protocol} from 'electron';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {patternBytes} from '../fixtures/take-files-checks.ts';

type SchemeModule = typeof import('../../main/take-scheme.ts');
type Handler = Awaited<ReturnType<SchemeModule['installTakeHandler']>>;

const here = path.dirname(fileURLToPath(import.meta.url));
const recordingsFolder = process.env.PLAYER_HARNESS_RECORDINGS ?? '';
const pickedFoldersFile = process.env.PLAYER_HARNESS_PICKED ?? '';
const firstPage = process.env.PLAYER_HARNESS_PAGE ?? 'harness';

for (const s of ['disable-renderer-backgrounding', 'disable-background-timer-throttling', 'disable-backgrounding-occluded-windows']) app.commandLine.appendSwitch(s);

let productError: string | null = null;
let scheme: SchemeModule | null = null;
let handler: Handler | null = null;
try {
    // Electron waits for this top-level await before `ready`, so the scheme registers in time.
    scheme = await import('../../main/take-scheme.ts');
    scheme.registerTakeScheme();
} catch (e) {
    productError = String(e);
}

const pages: Record<string, string> = {
    harness: path.join(here, '..', 'renderer', 'player', 'tests', 'harness', 'index.html'),
    host: path.join(here, '..', 'renderer', 'components', 'playback', 'tests', 'host', 'index.html'),
};

function openWindow(name = firstPage): number {
    const win = new BrowserWindow({
        width: 1400, height: 1000, show: process.env.PLAYER_HARNESS_SHOW === '1',
        // a hidden window must run requestAnimationFrame and timers as a shown one (CI runs hidden)
        webPreferences: {preload: path.join(here, '..', 'preload', 'preload.mjs'), contextIsolation: true, sandbox: true, backgroundThrottling: false},
    });
    // a never-shown window paints about once a second once a canvas draws: show it transparent, inactive
    // and click-through instead, so hidden runs behave as shown runs
    if (process.env.PLAYER_HARNESS_SHOW !== '1') {
        win.setOpacity(0);
        win.setIgnoreMouseEvents(true);
        win.showInactive();
    }
    void win.loadFile(pages[name]);
    return win.id;
}

/** T-PLAY-59: a handler variant that answers 200 with the exact length, 200 with the whole file, or
 * 206 with a wrong Content-Range start. It serves the pattern of `take-files-checks.ts` (seed 2). */
function installVariant(mode: 'ok-exact' | 'ok-whole' | 'bad-start'): void {
    const size = 300_000;
    const whole = patternBytes(2, 0, size);
    protocol.unhandle('skellycam-take');
    protocol.handle('skellycam-take', req => {
        const m = /^bytes=(\d+)-(\d+)$/.exec(req.headers.get('Range') ?? '');
        const headers = {'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Range, Content-Length, Accept-Ranges'};
        if (!m || mode === 'ok-whole') return new Response(whole, {status: 200, headers});
        const a = Number(m[1]);
        const b = Math.min(Number(m[2]), size - 1);
        if (mode === 'ok-exact') return new Response(whole.slice(a, b + 1), {status: 200, headers});
        return new Response(whole.slice(a + 1, b + 2), {status: 206, headers: {...headers, 'Content-Range': `bytes ${a + 1}-${b + 1}/${size}`}});
    });
}

const need = (): Handler => {
    if (!handler) throw new Error(productError ?? 'the take handler is not installed');
    return handler;
};

(globalThis as Record<string, unknown>).__harness = {
    productError: () => productError,
    recordPick: (folder: string) => need().recordPick(folder),
    setReadFault: (relativePath: string | null) => need().setReadFault(relativePath),
    openWindow: (name?: string) => openWindow(name),
    installVariant,
    channels: async () => (await import('../../main/bridge.ts')).TAKE_CHANNELS,
};

ipcMain.handle('harness:product-error', () => productError);

void app.whenReady().then(async () => {
    if (scheme) {
        try {
            handler = await scheme.installTakeHandler({recordingsFolder, pickedFoldersFile});
        } catch (e) {
            productError = String(e);
        }
    }
    openWindow();
});

app.on('window-all-closed', () => app.quit());
